import pytest
from app.extensions import db
from app.models import (
    User,
    Category,
    Expense,
    Bill,
    BillCadence,
    RecurringExpense,
    RecurringCadence,
    Reminder,
    AuditLog,
)
from datetime import date, datetime


@pytest.fixture()
def seeded_user(client, auth_header):
    """Create sample data for the default test user."""
    with client.application.app_context():
        user = db.session.query(User).filter_by(
            email="test@example.com"
        ).first()
        uid = user.id

        cat = Category(user_id=uid, name="Groceries")
        db.session.add(cat)
        db.session.flush()

        exp = Expense(
            user_id=uid,
            category_id=cat.id,
            amount=42.50,
            currency="INR",
            notes="weekly shopping",
            spent_at=date(2026, 3, 1),
        )
        db.session.add(exp)

        rec = RecurringExpense(
            user_id=uid,
            amount=9.99,
            notes="streaming",
            cadence=RecurringCadence.MONTHLY,
            start_date=date(2026, 1, 1),
        )
        db.session.add(rec)

        bill = Bill(
            user_id=uid,
            name="Electricity",
            amount=80.00,
            next_due_date=date(2026, 4, 1),
            cadence=BillCadence.MONTHLY,
        )
        db.session.add(bill)
        db.session.flush()

        rem = Reminder(
            user_id=uid,
            bill_id=bill.id,
            message="pay electricity",
            send_at=datetime(2026, 3, 30, 9, 0),
        )
        db.session.add(rem)
        db.session.commit()
    return auth_header


# ── Export Tests ────────────────────────────────────────────


def test_export_returns_user_data(client, seeded_user):
    r = client.get("/gdpr/export", headers=seeded_user)
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["user"]["email"] == "test@example.com"


def test_export_includes_categories(client, seeded_user):
    r = client.get("/gdpr/export", headers=seeded_user)
    data = r.get_json()["data"]
    names = [c["name"] for c in data["categories"]]
    assert "Groceries" in names


def test_export_includes_expenses(client, seeded_user):
    r = client.get("/gdpr/export", headers=seeded_user)
    data = r.get_json()["data"]
    assert len(data["expenses"]) >= 1
    assert data["expenses"][0]["notes"] == "weekly shopping"


def test_export_includes_recurring(client, seeded_user):
    r = client.get("/gdpr/export", headers=seeded_user)
    data = r.get_json()["data"]
    assert len(data["recurring_expenses"]) >= 1


def test_export_includes_bills(client, seeded_user):
    r = client.get("/gdpr/export", headers=seeded_user)
    data = r.get_json()["data"]
    assert any(b["name"] == "Electricity" for b in data["bills"])


def test_export_includes_reminders(client, seeded_user):
    r = client.get("/gdpr/export", headers=seeded_user)
    data = r.get_json()["data"]
    assert len(data["reminders"]) >= 1


def test_export_excludes_password_hash(client, seeded_user):
    r = client.get("/gdpr/export", headers=seeded_user)
    data = r.get_json()["data"]
    assert "password_hash" not in data["user"]


def test_export_creates_audit_log(client, seeded_user):
    client.get("/gdpr/export", headers=seeded_user)
    with client.application.app_context():
        logs = db.session.query(AuditLog).filter_by(
            action="PII_EXPORT"
        ).all()
        assert len(logs) >= 1


def test_export_requires_auth(client):
    r = client.get("/gdpr/export")
    assert r.status_code == 401


# ── Delete Tests ────────────────────────────────────────────


def test_delete_requires_password(client, seeded_user):
    r = client.post("/gdpr/delete", headers=seeded_user, json={})
    assert r.status_code == 400
    assert "password required" in r.get_json()["error"]


def test_delete_rejects_wrong_password(client, seeded_user):
    r = client.post(
        "/gdpr/delete", headers=seeded_user, json={"password": "wrong"}
    )
    assert r.status_code == 403


def test_delete_removes_user(client, seeded_user):
    r = client.post(
        "/gdpr/delete", headers=seeded_user, json={"password": "password123"}
    )
    assert r.status_code == 200
    with client.application.app_context():
        user = db.session.query(User).filter_by(
            email="test@example.com"
        ).first()
        assert user is None


def test_delete_cascades_expenses(client, seeded_user):
    with client.application.app_context():
        user = db.session.query(User).filter_by(
            email="test@example.com"
        ).first()
        uid = user.id

    client.post(
        "/gdpr/delete", headers=seeded_user, json={"password": "password123"}
    )

    with client.application.app_context():
        remaining = db.session.query(Expense).filter_by(
            user_id=uid
        ).count()
        assert remaining == 0


def test_delete_cascades_categories(client, seeded_user):
    with client.application.app_context():
        user = db.session.query(User).filter_by(
            email="test@example.com"
        ).first()
        uid = user.id

    client.post(
        "/gdpr/delete", headers=seeded_user, json={"password": "password123"}
    )

    with client.application.app_context():
        remaining = db.session.query(Category).filter_by(
            user_id=uid
        ).count()
        assert remaining == 0


def test_delete_preserves_audit_log(client, seeded_user):
    client.post(
        "/gdpr/delete", headers=seeded_user, json={"password": "password123"}
    )
    with client.application.app_context():
        logs = db.session.query(AuditLog).filter_by(
            action="ACCOUNT_DELETED"
        ).all()
        assert len(logs) >= 1
        # user_id should be NULL after cascade
        assert logs[0].user_id is None


def test_delete_requires_auth(client):
    r = client.post("/gdpr/delete", json={"password": "password123"})
    assert r.status_code == 401


# ── Audit Tests ─────────────────────────────────────────────


def test_audit_returns_logs(client, seeded_user):
    # Trigger an export to create an audit entry
    client.get("/gdpr/export", headers=seeded_user)
    r = client.get("/gdpr/audit", headers=seeded_user)
    assert r.status_code == 200
    logs = r.get_json()["audit_logs"]
    assert len(logs) >= 1
    assert logs[0]["action"] == "PII_EXPORT"


def test_audit_requires_auth(client):
    r = client.get("/gdpr/audit")
    assert r.status_code == 401
