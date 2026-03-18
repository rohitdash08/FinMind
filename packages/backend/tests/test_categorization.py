"""
Tests for the Intelligent Transaction Categorization Engine.

Covers:
- Built-in keyword categorization
- Auto-categorize endpoint (single + bulk)
- User correction & learning
- Category rule CRUD
- Confidence scoring
- Fallback behaviour
"""

import pytest
from unittest.mock import MagicMock, patch
from app import create_app
from app.config import Settings
from app.extensions import db


class CategorizationTestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret-with-32-plus-chars-1234567890"


def _make_redis_mock():
    """Return a MagicMock that silently absorbs all Redis calls."""
    m = MagicMock()
    m.get.return_value = None
    m.setex.return_value = True
    m.set.return_value = True
    m.delete.return_value = 1
    m.keys.return_value = []
    m.scan.return_value = (0, [])  # cursor=0 (done), keys=[]
    m.flushdb.return_value = True
    return m


@pytest.fixture()
def app_fixture():
    redis_mock = _make_redis_mock()
    with patch("app.extensions.redis_client", redis_mock), \
         patch("app.routes.auth.redis_client", redis_mock), \
         patch("app.services.cache.redis_client", redis_mock):
        app = create_app(CategorizationTestSettings())
        app.config.update(TESTING=True)
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.session.remove()
            db.drop_all()


@pytest.fixture()
def client(app_fixture):
    return app_fixture.test_client()


@pytest.fixture()
def auth_header(client):
    email, password = "cat_test@example.com", "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (200, 201, 409), r.get_json()
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_expense(client, auth_header, description, amount=50.0, expense_type="EXPENSE"):
    r = client.post(
        "/expenses",
        json={"description": description, "amount": amount, "date": "2025-01-01", "expense_type": expense_type},
        headers=auth_header,
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409), r.get_json()
    if r.status_code == 409:
        # Already exists — fetch it
        r2 = client.get("/categories", headers=auth_header)
        for c in r2.get_json():
            if c["name"] == name:
                return c
    return r.get_json()


# ---------------------------------------------------------------------------
# Defaults endpoint
# ---------------------------------------------------------------------------


def test_list_defaults(client, auth_header):
    r = client.get("/categorization/defaults", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert "default_categories" in body
    defaults = body["default_categories"]
    assert "Food" in defaults
    assert "Transport" in defaults
    assert "Entertainment" in defaults
    assert "Bills" in defaults
    assert "Shopping" in defaults
    assert "Health" in defaults
    assert "Education" in defaults
    assert "Income" in defaults
    assert "Transfer" in defaults
    assert "Other" in defaults


# ---------------------------------------------------------------------------
# Auto-categorize single expense
# ---------------------------------------------------------------------------


def test_categorize_food_keyword(client, auth_header):
    expense = _create_expense(client, auth_header, "Starbucks coffee morning", amount=250)
    r = client.post(
        f"/categorization/expenses/{expense['id']}/categorize",
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["expense_id"] == expense["id"]
    assert body["category_name"] == "Food"
    assert body["confidence"] in ("high", "medium", "low")
    assert body["method"] == "builtin_keyword"


def test_categorize_transport_keyword(client, auth_header):
    expense = _create_expense(client, auth_header, "Uber ride to airport", amount=350)
    r = client.post(
        f"/categorization/expenses/{expense['id']}/categorize",
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["category_name"] == "Transport"


def test_categorize_entertainment_keyword(client, auth_header):
    expense = _create_expense(client, auth_header, "Netflix monthly subscription", amount=499)
    r = client.post(
        f"/categorization/expenses/{expense['id']}/categorize",
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["category_name"] == "Entertainment"


def test_categorize_bills_keyword(client, auth_header):
    expense = _create_expense(client, auth_header, "Jio mobile recharge", amount=299)
    r = client.post(
        f"/categorization/expenses/{expense['id']}/categorize",
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["category_name"] == "Bills"


def test_categorize_not_found(client, auth_header):
    r = client.post("/categorization/expenses/99999/categorize", headers=auth_header)
    assert r.status_code == 404


def test_categorize_updates_expense_category(client, auth_header):
    """Categorization should persist the category_id on the expense."""
    expense = _create_expense(client, auth_header, "McDonald's meal", amount=199)
    assert expense["category_id"] is None

    client.post(
        f"/categorization/expenses/{expense['id']}/categorize",
        headers=auth_header,
    )

    r = client.get("/expenses", headers=auth_header)
    expenses = r.get_json()
    target = next(e for e in expenses if e["id"] == expense["id"])
    assert target["category_id"] is not None


# ---------------------------------------------------------------------------
# Bulk categorize
# ---------------------------------------------------------------------------


def test_bulk_categorize_specific_ids(client, auth_header):
    e1 = _create_expense(client, auth_header, "Spotify premium", amount=129)
    e2 = _create_expense(client, auth_header, "Train ticket IRCTC", amount=850)
    r = client.post(
        "/categorization/expenses/bulk-categorize",
        json={"expense_ids": [e1["id"], e2["id"]]},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["categorized"] == 2
    names = {res["category_name"] for res in body["results"]}
    assert "Entertainment" in names
    assert "Transport" in names


def test_bulk_categorize_all_uncategorized(client, auth_header):
    _create_expense(client, auth_header, "Amazon shopping spree", amount=3000)
    _create_expense(client, auth_header, "Doctor visit clinic", amount=500)
    r = client.post(
        "/categorization/expenses/bulk-categorize",
        json={},  # no expense_ids → all uncategorized
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["categorized"] >= 2


def test_bulk_categorize_invalid_payload(client, auth_header):
    r = client.post(
        "/categorization/expenses/bulk-categorize",
        json={"expense_ids": "not-a-list"},
        headers=auth_header,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# User correction and learning
# ---------------------------------------------------------------------------


def test_correct_categorization(client, auth_header):
    expense = _create_expense(client, auth_header, "Pharmacy purchase", amount=200)
    cat = _create_category(client, auth_header, "Health")

    r = client.post(
        f"/categorization/expenses/{expense['id']}/correct",
        json={"category_id": cat["id"]},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["category_id"] == cat["id"]
    assert body["category_name"] == "Health"


def test_correction_is_learned_for_future(client, auth_header):
    """After correcting one expense, a new expense with same description should use learned category."""
    cat = _create_category(client, auth_header, "MyCustomCat")

    # Create and correct the first expense
    e1 = _create_expense(client, auth_header, "Mysterious vendor XYZ", amount=500)
    client.post(
        f"/categorization/expenses/{e1['id']}/correct",
        json={"category_id": cat["id"]},
        headers=auth_header,
    )

    # Create a second expense with same description
    e2 = _create_expense(client, auth_header, "Mysterious vendor XYZ", amount=500)
    r = client.post(
        f"/categorization/expenses/{e2['id']}/categorize",
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["category_name"] == "MyCustomCat"
    assert body["method"] == "learned"
    assert body["confidence"] == "high"


def test_correct_not_found_expense(client, auth_header):
    cat = _create_category(client, auth_header, "Food")
    r = client.post(
        "/categorization/expenses/99999/correct",
        json={"category_id": cat["id"]},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_correct_missing_category_id(client, auth_header):
    expense = _create_expense(client, auth_header, "Some expense", amount=100)
    r = client.post(
        f"/categorization/expenses/{expense['id']}/correct",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Category rules CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_keyword_rule(client, auth_header):
    cat = _create_category(client, auth_header, "Transport")

    r = client.post(
        "/categorization/rules",
        json={"category_id": cat["id"], "rule_type": "keyword", "pattern": "quickride", "priority": 10},
        headers=auth_header,
    )
    assert r.status_code == 201
    rule = r.get_json()
    assert rule["rule_type"] == "keyword"
    assert rule["pattern"] == "quickride"
    assert rule["priority"] == 10

    r = client.get("/categorization/rules", headers=auth_header)
    assert r.status_code == 200
    rules = r.get_json()
    assert any(ru["pattern"] == "quickride" for ru in rules)


def test_user_defined_rule_takes_precedence(client, auth_header):
    """A user rule for 'amazon' → Bills should override the built-in Shopping."""
    bills_cat = _create_category(client, auth_header, "Bills")
    client.post(
        "/categorization/rules",
        json={"category_id": bills_cat["id"], "rule_type": "keyword", "pattern": "amazon", "priority": 50},
        headers=auth_header,
    )
    expense = _create_expense(client, auth_header, "Amazon AWS bill", amount=2000)
    r = client.post(
        f"/categorization/expenses/{expense['id']}/categorize",
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    # User rule should win over built-in keyword
    assert body["category_name"] == "Bills"
    assert body["confidence"] == "high"
    assert "rule:" in body["method"]


def test_create_amount_range_rule(client, auth_header):
    cat = _create_category(client, auth_header, "Shopping")
    r = client.post(
        "/categorization/rules",
        json={
            "category_id": cat["id"],
            "rule_type": "amount_range",
            "amount_min": 1000,
            "amount_max": 5000,
            "priority": 5,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    rule = r.get_json()
    assert rule["rule_type"] == "amount_range"
    assert rule["amount_min"] == 1000.0
    assert rule["amount_max"] == 5000.0


def test_create_rule_invalid_type(client, auth_header):
    cat = _create_category(client, auth_header, "Food")
    r = client.post(
        "/categorization/rules",
        json={"category_id": cat["id"], "rule_type": "invalid_type", "pattern": "x"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_rule_keyword_missing_pattern(client, auth_header):
    cat = _create_category(client, auth_header, "Food")
    r = client.post(
        "/categorization/rules",
        json={"category_id": cat["id"], "rule_type": "keyword"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_rule_missing_category_id(client, auth_header):
    r = client.post(
        "/categorization/rules",
        json={"rule_type": "keyword", "pattern": "test"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_delete_rule(client, auth_header):
    cat = _create_category(client, auth_header, "Food")
    r = client.post(
        "/categorization/rules",
        json={"category_id": cat["id"], "rule_type": "merchant", "pattern": "quickbite"},
        headers=auth_header,
    )
    rule_id = r.get_json()["id"]

    r = client.delete(f"/categorization/rules/{rule_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/categorization/rules", headers=auth_header)
    assert not any(ru["id"] == rule_id for ru in r.get_json())


def test_delete_rule_not_found(client, auth_header):
    r = client.delete("/categorization/rules/99999", headers=auth_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------


def test_high_confidence_for_learned(client, auth_header):
    cat = _create_category(client, auth_header, "SpecialCat")
    e1 = _create_expense(client, auth_header, "UnknownMerchant99", amount=100)
    client.post(
        f"/categorization/expenses/{e1['id']}/correct",
        json={"category_id": cat["id"]},
        headers=auth_header,
    )
    e2 = _create_expense(client, auth_header, "UnknownMerchant99", amount=100)
    r = client.post(f"/categorization/expenses/{e2['id']}/categorize", headers=auth_header)
    assert r.get_json()["confidence"] == "high"


def test_medium_confidence_for_builtin_keyword(client, auth_header):
    expense = _create_expense(client, auth_header, "Uber ride", amount=200)
    r = client.post(f"/categorization/expenses/{expense['id']}/categorize", headers=auth_header)
    assert r.get_json()["confidence"] == "medium"


def test_low_confidence_for_fallback(client, auth_header):
    # Completely unrecognized description, high amount to avoid amount heuristic
    expense = _create_expense(client, auth_header, "xyzzy zork quux qwerty", amount=99999)
    r = client.post(f"/categorization/expenses/{expense['id']}/categorize", headers=auth_header)
    body = r.get_json()
    assert body["confidence"] == "low"


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


def test_endpoints_require_auth(client):
    assert client.post("/categorization/expenses/1/categorize").status_code == 401
    assert client.post("/categorization/expenses/bulk-categorize").status_code == 401
    assert client.post("/categorization/expenses/1/correct").status_code == 401
    assert client.get("/categorization/rules").status_code == 401
    assert client.post("/categorization/rules").status_code == 401
    assert client.delete("/categorization/rules/1").status_code == 401
    assert client.get("/categorization/defaults").status_code == 401
