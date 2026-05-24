"""Tests for GDPR PII export and account deletion."""
import json
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_expense(client, auth_header, amount=50, notes="test"):
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": notes,
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201, r.get_json()
    return r


def _add_bill(client, auth_header, name="Netflix", amount=15):
    r = client.post(
        "/bills",
        json={
            "name": name,
            "amount": amount,
            "next_due_date": (date.today() + timedelta(days=7)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201, r.get_json()
    return r


def _add_category(client, auth_header, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201, r.get_json()
    return r


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------

def test_export_requires_auth(client):
    r = client.get("/gdpr/export")
    assert r.status_code == 401


def test_export_empty_account(client, auth_header):
    """Export works even with no data — returns valid JSON with zero-count collections."""
    r = client.get("/gdpr/export", headers=auth_header)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert r.content_type == "application/json"

    data = r.get_json()
    assert data["schema_version"] == "1.0"
    assert "exported_at" in data
    assert "user" in data
    assert data["counts"]["expenses"] == 0
    assert data["counts"]["bills"] == 0
    assert data["counts"]["categories"] == 0


def test_export_includes_all_data(client, auth_header):
    """Export package contains expenses, bills, and categories."""
    _add_expense(client, auth_header, 100, "Grocery shop")
    _add_expense(client, auth_header, 40, "Coffee")
    _add_bill(client, auth_header, "Netflix", 15)
    _add_category(client, auth_header, "Transport")

    r = client.get("/gdpr/export", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert data["counts"]["expenses"] == 2
    assert data["counts"]["bills"] == 1
    assert data["counts"]["categories"] == 1

    expense_notes = {e["description"] for e in data["expenses"]}
    assert "Grocery shop" in expense_notes
    assert "Coffee" in expense_notes

    bill_names = {b["name"] for b in data["bills"]}
    assert "Netflix" in bill_names


def test_export_user_profile_fields(client, auth_header):
    """Export includes user profile without the password hash."""
    r = client.get("/gdpr/export", headers=auth_header)
    data = r.get_json()
    user = data["user"]

    assert "email" in user
    assert "preferred_currency" in user
    assert "created_at" in user
    # Password hash must NOT be in the export
    assert "password_hash" not in user
    assert "password" not in user


def test_export_filename_contains_date(client, auth_header):
    """Downloaded filename contains a date stamp."""
    r = client.get("/gdpr/export", headers=auth_header)
    disposition = r.headers.get("Content-Disposition", "")
    assert "finmind-export-" in disposition
    assert ".json" in disposition


def test_export_is_valid_json(client, auth_header):
    """Response body is parseable JSON."""
    r = client.get("/gdpr/export", headers=auth_header)
    try:
        json.loads(r.data)
    except json.JSONDecodeError:
        raise AssertionError("Export response is not valid JSON")


# ---------------------------------------------------------------------------
# Delete account endpoint
# ---------------------------------------------------------------------------

def test_delete_requires_auth(client):
    r = client.post("/gdpr/delete-account", json={"password": "pw"})
    assert r.status_code == 401


def test_delete_requires_password_field(client, auth_header):
    r = client.post("/gdpr/delete-account", json={}, headers=auth_header)
    assert r.status_code == 400
    assert "password" in r.get_json().get("error", "").lower()


def test_delete_wrong_password(client, auth_header):
    r = client.post(
        "/gdpr/delete-account",
        json={"password": "wrong-password-xyz"},
        headers=auth_header,
    )
    assert r.status_code == 401


def test_delete_correct_password_returns_204(client, auth_header):
    """Correct password produces HTTP 204 No Content."""
    r = client.post(
        "/gdpr/delete-account",
        json={"password": "password123"},  # matches conftest registration password
        headers=auth_header,
    )
    assert r.status_code == 204
    assert r.data == b""


def test_delete_removes_user_from_db(client, auth_header, app_fixture):
    """After deletion the user row no longer exists in the database."""
    from app.extensions import db
    from app.models import User

    # Confirm user exists
    with app_fixture.app_context():
        assert db.session.query(User).filter_by(email="test@example.com").first() is not None

    client.post(
        "/gdpr/delete-account",
        json={"password": "password123"},
        headers=auth_header,
    )

    with app_fixture.app_context():
        assert db.session.query(User).filter_by(email="test@example.com").first() is None


def test_delete_removes_associated_expenses(client, auth_header, app_fixture):
    """All expenses belonging to the deleted user are purged."""
    from app.extensions import db
    from app.models import Expense

    _add_expense(client, auth_header, 200, "Rent")
    _add_expense(client, auth_header, 50, "Coffee")

    # Get user id from DB before deletion
    with app_fixture.app_context():
        from app.models import User
        user = db.session.query(User).filter_by(email="test@example.com").first()
        uid = user.id

    client.post(
        "/gdpr/delete-account",
        json={"password": "password123"},
        headers=auth_header,
    )

    with app_fixture.app_context():
        remaining = db.session.query(Expense).filter_by(user_id=uid).count()
        assert remaining == 0


def test_delete_removes_bills_and_categories(client, auth_header, app_fixture):
    """Bills and categories are purged on account deletion."""
    from app.extensions import db
    from app.models import Bill, Category

    _add_bill(client, auth_header, "Spotify", 10)
    _add_category(client, auth_header, "Entertainment")

    with app_fixture.app_context():
        from app.models import User
        user = db.session.query(User).filter_by(email="test@example.com").first()
        uid = user.id

    client.post(
        "/gdpr/delete-account",
        json={"password": "password123"},
        headers=auth_header,
    )

    with app_fixture.app_context():
        assert db.session.query(Bill).filter_by(user_id=uid).count() == 0
        assert db.session.query(Category).filter_by(user_id=uid).count() == 0


def test_delete_token_no_longer_valid(client, auth_header):
    """After deletion the old JWT cannot access protected endpoints."""
    client.post(
        "/gdpr/delete-account",
        json={"password": "password123"},
        headers=auth_header,
    )
    # The user no longer exists; /auth/me should return 404 (user not found)
    r = client.get("/auth/me", headers=auth_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# build_export_package unit test (no HTTP layer)
# ---------------------------------------------------------------------------

def test_build_export_package_structure(client, auth_header, app_fixture):
    """build_export_package returns a dict with all required top-level keys."""
    from app.extensions import db
    from app.models import User
    from app.services.gdpr import build_export_package

    _add_expense(client, auth_header, 75, "Lunch")

    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email="test@example.com").first()
        package = build_export_package(user.id)

    required_keys = {
        "schema_version", "exported_at", "user",
        "expenses", "recurring_expenses", "bills",
        "reminders", "categories", "subscriptions", "counts",
    }
    assert required_keys.issubset(package.keys())
    assert package["counts"]["expenses"] == 1
