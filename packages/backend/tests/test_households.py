from datetime import date, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import User


@pytest.fixture(autouse=True)
def _disable_cache_calls(monkeypatch):
    monkeypatch.setattr(
        "app.routes.expenses.cache_delete_patterns", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "app.routes.bills.cache_delete_patterns", lambda *_args, **_kwargs: None
    )


def _register_and_auth_header(
    client, app_fixture, email: str, password: str = "password123"
):
    register = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert register.status_code in (201, 409)
    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email=email).first()
        assert user is not None
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _create_household(client, auth_header, name: str = "Home HQ") -> int:
    r = client.post("/households", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["name"] == name
    return payload["id"]


def test_household_admin_can_add_member_and_member_can_view_household(
    client, app_fixture
):
    owner_auth = _register_and_auth_header(client, app_fixture, "owner@example.com")
    member_email = "household-member@example.com"
    member_auth = _register_and_auth_header(client, app_fixture, member_email)
    household_id = _create_household(client, owner_auth, name="Roommates")

    r = client.post(
        f"/households/{household_id}/members",
        json={"email": member_email},
        headers=owner_auth,
    )
    assert r.status_code == 201

    owner_households = client.get("/households/my", headers=owner_auth)
    assert owner_households.status_code == 200
    owner_payload = owner_households.get_json()
    assert any(
        h["id"] == household_id and h["role"] == "ADMIN"
        for h in owner_payload["households"]
    )

    member_households = client.get("/households/my", headers=member_auth)
    assert member_households.status_code == 200
    member_payload = member_households.get_json()
    assert any(
        h["id"] == household_id and h["role"] == "MEMBER"
        for h in member_payload["households"]
    )

    household_details = client.get(f"/households/{household_id}", headers=member_auth)
    assert household_details.status_code == 200
    details = household_details.get_json()
    member_emails = {m["email"] for m in details["members"]}
    assert member_email in member_emails


def test_household_records_are_shared_with_all_members(client, app_fixture):
    owner_auth = _register_and_auth_header(client, app_fixture, "owner@example.com")
    member_email = "shared-finance@example.com"
    member_auth = _register_and_auth_header(client, app_fixture, member_email)
    household_id = _create_household(client, owner_auth, name="Shared Finance")
    add_member = client.post(
        f"/households/{household_id}/members",
        json={"email": member_email},
        headers=owner_auth,
    )
    assert add_member.status_code == 201

    create_category = client.post(
        "/categories",
        json={"name": "Groceries", "household_id": household_id},
        headers=owner_auth,
    )
    assert create_category.status_code == 201
    category_id = create_category.get_json()["id"]

    create_expense = client.post(
        "/expenses",
        json={
            "amount": 128.75,
            "description": "Weekly groceries",
            "date": "2026-03-01",
            "category_id": category_id,
            "household_id": household_id,
        },
        headers=owner_auth,
    )
    assert create_expense.status_code == 201
    expense_id = create_expense.get_json()["id"]

    create_bill = client.post(
        "/bills",
        json={
            "name": "Fiber Internet",
            "amount": 59.9,
            "next_due_date": (date.today() + timedelta(days=7)).isoformat(),
            "cadence": "MONTHLY",
            "household_id": household_id,
        },
        headers=owner_auth,
    )
    assert create_bill.status_code == 201
    bill_id = create_bill.get_json()["id"]

    categories_for_member = client.get("/categories", headers=member_auth)
    assert categories_for_member.status_code == 200
    category_payload = categories_for_member.get_json()
    assert any(
        item["id"] == category_id and item["household_id"] == household_id
        for item in category_payload
    )

    expenses_for_member = client.get("/expenses", headers=member_auth)
    assert expenses_for_member.status_code == 200
    expense_payload = expenses_for_member.get_json()
    assert any(
        item["id"] == expense_id and item["household_id"] == household_id
        for item in expense_payload
    )

    bills_for_member = client.get("/bills", headers=member_auth)
    assert bills_for_member.status_code == 200
    bill_payload = bills_for_member.get_json()
    assert any(
        item["id"] == bill_id and item["household_id"] == household_id
        for item in bill_payload
    )


def test_non_member_cannot_access_or_write_household_records(client, app_fixture):
    owner_auth = _register_and_auth_header(client, app_fixture, "owner@example.com")
    outsider_auth = _register_and_auth_header(
        client, app_fixture, "outsider@example.com"
    )
    household_id = _create_household(client, owner_auth, name="Private Home")

    get_household = client.get(f"/households/{household_id}", headers=outsider_auth)
    assert get_household.status_code == 403

    create_expense = client.post(
        "/expenses",
        json={
            "amount": 25,
            "description": "Should fail",
            "date": "2026-03-02",
            "household_id": household_id,
        },
        headers=outsider_auth,
    )
    assert create_expense.status_code == 403

    create_category = client.post(
        "/categories",
        json={"name": "Should Not Work", "household_id": household_id},
        headers=outsider_auth,
    )
    assert create_category.status_code == 403

    create_bill = client.post(
        "/bills",
        json={
            "name": "Should Fail",
            "amount": 12.5,
            "next_due_date": date.today().isoformat(),
            "cadence": "MONTHLY",
            "household_id": household_id,
        },
        headers=outsider_auth,
    )
    assert create_bill.status_code == 403
