from app.extensions import db
from app.models import (
    AdImpression,
    AuditLog,
    Bill,
    Category,
    Expense,
    RecurringExpense,
    SubscriptionPlan,
    User,
    UserSubscription,
)


def _register_and_login(client, *, email: str, password: str = "secret123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    payload = r.get_json()
    return (
        {"Authorization": f"Bearer {payload['access_token']}"},
        payload["refresh_token"],
    )


def test_auth_refresh_flow(client):
    # Register user
    email = "refresh@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)  # 409 if already exists

    # Login to get tokens
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data and "refresh_token" in data

    # Use refresh to get a new access token
    refresh_token = data["refresh_token"]
    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200
    new_access = r.get_json().get("access_token")
    assert isinstance(new_access, str) and len(new_access) > 10


def test_auth_logout_revokes_refresh_token(client):
    email = "logout@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    refresh_token = r.get_json()["refresh_token"]

    r = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 401


def test_auth_me_and_update_preferred_currency(client):
    email = "profile@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    me = r.get_json()
    assert me["email"] == email
    assert me["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "inr"}, headers=auth)
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "ZZZ"}, headers=auth)
    assert r.status_code == 400


def test_auth_export_data_returns_full_user_package(client, auth_header, app_fixture):
    me = client.get("/auth/me", headers=auth_header)
    assert me.status_code == 200
    user_id = me.get_json()["id"]

    r = client.post("/categories", json={"name": "Utilities"}, headers=auth_header)
    assert r.status_code == 201
    category_id = r.get_json()["id"]

    r = client.post(
        "/expenses",
        json={
            "amount": 199.5,
            "category_id": category_id,
            "description": "Electricity bill",
            "date": "2026-03-01",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    expense_id = r.get_json()["id"]

    r = client.post(
        "/expenses/recurring",
        json={
            "amount": 49.0,
            "description": "Gym membership",
            "start_date": "2026-03-01",
            "cadence": "MONTHLY",
            "category_id": category_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    recurring_id = r.get_json()["id"]

    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 89.0,
            "next_due_date": "2026-03-20",
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    bill_id = r.get_json()["id"]

    r = client.post(
        "/reminders",
        json={
            "message": "Pay internet bill",
            "send_at": "2026-03-15T09:00:00",
            "channel": "email",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    reminder_id = r.get_json()["id"]

    with app_fixture.app_context():
        plan = SubscriptionPlan(name="Pro", price_cents=999, interval="monthly")
        db.session.add(plan)
        db.session.flush()
        db.session.add(UserSubscription(user_id=user_id, plan_id=plan.id, active=True))
        db.session.add(AdImpression(user_id=user_id, placement="dashboard_top"))
        db.session.commit()

    r = client.get("/auth/export-data", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["profile"]["id"] == user_id
    assert payload["profile"]["email"] == "test@example.com"
    assert payload["profile"]["preferred_currency"] == "INR"
    assert any(item["id"] == category_id for item in payload["categories"])
    assert any(item["id"] == expense_id for item in payload["expenses"])
    assert any(item["id"] == recurring_id for item in payload["recurring_expenses"])
    assert any(item["id"] == bill_id for item in payload["bills"])
    assert any(item["id"] == reminder_id for item in payload["reminders"])
    assert len(payload["subscriptions"]) == 1
    assert len(payload["ad_impressions"]) == 1

    with app_fixture.app_context():
        audit = (
            db.session.query(AuditLog)
            .filter(
                AuditLog.action == "USER_DATA_EXPORTED",
                AuditLog.user_id == user_id,
            )
            .all()
        )
        assert len(audit) == 1


def test_auth_delete_account_is_confirmed_and_irreversible(client, app_fixture):
    email = "erase-me@test.com"
    password = "secret123"
    auth, refresh_token = _register_and_login(client, email=email, password=password)

    me = client.get("/auth/me", headers=auth)
    assert me.status_code == 200
    user_id = me.get_json()["id"]

    r = client.post("/categories", json={"name": "Temporary"}, headers=auth)
    assert r.status_code == 201
    category_id = r.get_json()["id"]

    r = client.post(
        "/expenses",
        json={
            "amount": 10,
            "category_id": category_id,
            "description": "Temp record",
            "date": "2026-03-01",
        },
        headers=auth,
    )
    assert r.status_code == 201

    with app_fixture.app_context():
        db.session.add(AdImpression(user_id=user_id, placement="account_page"))
        db.session.commit()

    r = client.delete("/auth/delete-account", headers=auth, json={})
    assert r.status_code == 400

    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200

    r = client.delete("/auth/delete-account", headers=auth, json={"confirm": True})
    assert r.status_code == 200
    assert r.get_json()["message"] == "account deleted"

    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 404

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401

    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 401

    with app_fixture.app_context():
        assert db.session.get(User, user_id) is None
        assert db.session.query(Category).filter_by(user_id=user_id).count() == 0
        assert db.session.query(Expense).filter_by(user_id=user_id).count() == 0
        assert db.session.query(Bill).filter_by(user_id=user_id).count() == 0
        assert (
            db.session.query(RecurringExpense).filter_by(user_id=user_id).count() == 0
        )
        assert (
            db.session.query(UserSubscription).filter_by(user_id=user_id).count() == 0
        )
        assert db.session.query(AdImpression).filter_by(user_id=user_id).count() == 0
        deleted_logs = (
            db.session.query(AuditLog)
            .filter(AuditLog.action == "USER_ACCOUNT_DELETED")
            .all()
        )
        assert len(deleted_logs) == 1

    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
