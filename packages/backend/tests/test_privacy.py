import json
import zipfile
from datetime import date
from io import BytesIO

from app.extensions import db, redis_client
from app.models import (
    AdImpression,
    AuditLog,
    Bill,
    Category,
    Expense,
    RecurringCadence,
    RecurringExpense,
    Reminder,
    SubscriptionPlan,
    User,
    UserSubscription,
)


def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _create_expense(client, auth_header, category_id, description="Groceries"):
    r = client.post(
        "/expenses",
        json={
            "amount": 12.5,
            "currency": "USD",
            "category_id": category_id,
            "description": description,
            "date": "2026-02-12",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()["id"]


def _create_bill(client, auth_header):
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "currency": "USD",
            "next_due_date": date.today().isoformat(),
            "cadence": "MONTHLY",
            "channel_email": True,
            "channel_whatsapp": True,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()["id"]


def _register_and_login(client, email):
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _current_user_id(client, auth_header):
    r = client.get("/auth/me", headers=auth_header)
    assert r.status_code == 200
    return r.get_json()["id"]


def test_privacy_export_returns_zip_with_owned_data_and_audit_log(
    client, auth_header, app_fixture
):
    uid = _current_user_id(client, auth_header)
    category_id = _create_category(client, auth_header, "Food")
    _create_expense(client, auth_header, category_id)
    bill_id = _create_bill(client, auth_header)
    r = client.post(
        f"/reminders/bills/{bill_id}/schedule",
        json={"offsets_days": [1]},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/zip"
    assert "test@example.com" not in r.headers["Content-Disposition"]

    with zipfile.ZipFile(BytesIO(r.data)) as archive:
        names = set(archive.namelist())
        assert {
            "manifest.json",
            "profile.json",
            "data.json",
            "expenses.csv",
            "audit_logs.csv",
        }.issubset(names)
        profile = json.loads(archive.read("profile.json"))
        data = json.loads(archive.read("data.json"))
        expenses_csv = archive.read("expenses.csv").decode("utf-8")

    assert profile["email"] == "test@example.com"
    assert "password_hash" not in profile
    assert data["manifest"]["tables"]["expenses"] == 1
    assert data["manifest"]["tables"]["audit_logs"] == 1
    assert "Groceries" in expenses_csv

    with app_fixture.app_context():
        audit = db.session.query(AuditLog).filter_by(user_id=uid).one()
        assert audit.action == "privacy.export"


def test_privacy_delete_requires_confirmation_and_removes_only_requesting_user_data(
    client, auth_header, app_fixture
):
    uid = _current_user_id(client, auth_header)
    category_id = _create_category(client, auth_header, "Food")
    _create_expense(client, auth_header, category_id)
    bill_id = _create_bill(client, auth_header)
    r = client.post(
        f"/reminders/bills/{bill_id}/schedule",
        json={"offsets_days": [1]},
        headers=auth_header,
    )
    assert r.status_code == 200

    second_auth = _register_and_login(client, "other@example.com")
    second_uid = _current_user_id(client, second_auth)
    second_category_id = _create_category(client, second_auth, "Other")
    _create_expense(client, second_auth, second_category_id, "Other groceries")

    with app_fixture.app_context():
        plan = SubscriptionPlan(name="Premium", price_cents=999, interval="monthly")
        db.session.add(plan)
        db.session.flush()
        db.session.add(UserSubscription(user_id=uid, plan_id=plan.id, active=True))
        db.session.add(AdImpression(user_id=uid, placement="dashboard"))
        db.session.add(
            RecurringExpense(
                user_id=uid,
                category_id=category_id,
                amount=15,
                currency="USD",
                notes="Coffee",
                cadence=RecurringCadence.MONTHLY,
                start_date=date(2026, 1, 1),
            )
        )
        db.session.add(AuditLog(user_id=uid, action="privacy.export"))
        db.session.commit()
    redis_client.setex("auth:refresh:owned", 600, str(uid))
    redis_client.setex("auth:refresh:other", 600, str(second_uid))
    redis_client.setex(f"user:{uid}:categories", 600, "[]")
    redis_client.setex(f"insights:{uid}:2026-01", 600, "{}")
    redis_client.setex(f"user:{second_uid}:categories", 600, "[]")

    r = client.delete("/privacy/me", json={"confirm": "wrong"}, headers=auth_header)
    assert r.status_code == 400

    r = client.delete(
        "/privacy/me", json={"confirm": "DELETE_MY_DATA"}, headers=auth_header
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["message"] == "account permanently deleted"
    assert payload["deleted_records"]["expenses"] == 1
    assert payload["deleted_records"]["reminders"] == 2
    assert payload["anonymized_audit_logs"] == 1
    assert payload["deleted_cache_keys"] == 2
    assert payload["revoked_refresh_sessions"] == 2

    r = client.get("/auth/me", headers=auth_header)
    assert r.status_code == 404

    with app_fixture.app_context():
        assert db.session.get(User, uid) is None
        for model in [
            Category,
            Expense,
            RecurringExpense,
            Bill,
            Reminder,
            AdImpression,
            UserSubscription,
        ]:
            assert db.session.query(model).filter_by(user_id=uid).count() == 0
        assert db.session.get(User, second_uid) is not None
        assert db.session.query(Expense).filter_by(user_id=second_uid).count() == 1
        assert db.session.query(AuditLog).filter_by(user_id=uid).count() == 0
        completion = (
            db.session.query(AuditLog)
            .filter(
                AuditLog.user_id.is_(None),
                AuditLog.action.like("privacy.delete.completed%"),
            )
            .one()
        )
        assert "records=" in completion.action
    assert redis_client.exists("auth:refresh:owned") == 0
    assert redis_client.exists("auth:refresh:other") == 1
    assert redis_client.exists(f"user:{uid}:categories") == 0
    assert redis_client.exists(f"insights:{uid}:2026-01") == 0
    assert redis_client.exists(f"user:{second_uid}:categories") == 1
