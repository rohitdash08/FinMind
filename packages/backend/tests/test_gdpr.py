"""Tests for GDPR-compliant PII export and deletion endpoints."""

from datetime import date, datetime

from app.extensions import db
from app.models import (
    User,
    Category,
    Expense,
    RecurringExpense,
    Bill,
    Reminder,
    AdImpression,
    UserSubscription,
    AuditLog,
    SubscriptionPlan,
)


def _register_and_login(client, app_fixture, email="gdpr@test.com", password="secret123"):
    """Register a user and return (user_id, auth_headers)."""
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (200, 201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    token = data["access_token"]
    # Get user_id from DB (avoids needing app context for JWT decode)
    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email=email).first()
        user_id = user.id
    return user_id, {"Authorization": f"Bearer {token}"}


def _seed_user_data(app_fixture, user_id):
    """Seed various PII data for a user so export/delete has something to work with."""
    with app_fixture.app_context():
        cat = Category(user_id=user_id, name="Food")
        db.session.add(cat)
        db.session.flush()

        expense = Expense(
            user_id=user_id,
            category_id=cat.id,
            amount=42.50,
            currency="INR",
            notes="Lunch",
        )
        db.session.add(expense)

        recurring = RecurringExpense(
            user_id=user_id,
            category_id=cat.id,
            amount=100.00,
            currency="INR",
            notes="Netflix",
            cadence="MONTHLY",
            start_date=date(2026, 1, 1),
            active=True,
        )
        db.session.add(recurring)

        bill = Bill(
            user_id=user_id,
            name="Electricity",
            amount=75.00,
            currency="INR",
            next_due_date=date(2026, 6, 1),
            cadence="MONTHLY",
        )
        db.session.add(bill)
        db.session.flush()

        reminder = Reminder(
            user_id=user_id,
            bill_id=bill.id,
            message="Pay electricity bill",
            send_at=datetime(2026, 5, 30, 10, 0, 0),
        )
        db.session.add(reminder)

        ad = AdImpression(user_id=user_id, placement="sidebar")
        db.session.add(ad)

        # Create a subscription plan and user subscription
        plan = SubscriptionPlan(name="Pro", price_cents=999, interval="monthly")
        db.session.add(plan)
        db.session.flush()

        sub = UserSubscription(user_id=user_id, plan_id=plan.id, active=True)
        db.session.add(sub)

        db.session.commit()


# ─── Export tests ────────────────────────────────────────────────────────────


def test_export_returns_all_user_pii(client, auth_header, app_fixture):
    """GET /gdpr/users/<id>/export should return all PII as JSON."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        user_id = user.id

    _seed_user_data(app_fixture, user_id)

    r = client.get(f"/gdpr/users/{user_id}/export", headers=auth_header)
    assert r.status_code == 200

    data = r.get_json()
    assert "export_timestamp" in data
    assert "user" in data
    assert data["user"]["id"] == user_id
    assert data["user"]["email"] == "test@example.com"

    # All data categories present
    assert isinstance(data["categories"], list)
    assert len(data["categories"]) >= 1
    assert isinstance(data["expenses"], list)
    assert len(data["expenses"]) >= 1
    assert isinstance(data["recurring_expenses"], list)
    assert len(data["recurring_expenses"]) >= 1
    assert isinstance(data["bills"], list)
    assert len(data["bills"]) >= 1
    assert isinstance(data["reminders"], list)
    assert len(data["reminders"]) >= 1
    assert isinstance(data["ad_impressions"], list)
    assert len(data["ad_impressions"]) >= 1
    assert isinstance(data["subscriptions"], list)
    assert len(data["subscriptions"]) >= 1


def test_export_creates_audit_log(client, auth_header, app_fixture):
    """Exporting data should create a GDPR_DATA_EXPORT audit log entry."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        user_id = user.id

    r = client.get(f"/gdpr/users/{user_id}/export", headers=auth_header)
    assert r.status_code == 200

    with app_fixture.app_context():
        logs = (
            db.session.query(AuditLog)
            .filter_by(user_id=user_id, action="GDPR_DATA_EXPORT")
            .all()
        )
        assert len(logs) >= 1


def test_export_forbidden_for_other_user(client, app_fixture):
    """A user cannot export another user's data."""
    _, auth1 = _register_and_login(client, app_fixture, "user1@gdpr.test", "pass1")
    uid2, _ = _register_and_login(client, app_fixture, "user2@gdpr.test", "pass2")

    r = client.get(f"/gdpr/users/{uid2}/export", headers=auth1)
    assert r.status_code == 403


def test_export_requires_auth(client, app_fixture):
    """Unauthenticated requests should be rejected."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        if user:
            user_id = user.id
        else:
            user_id = 1

    r = client.get(f"/gdpr/users/{user_id}/export")
    assert r.status_code in (401, 422)


def test_export_user_not_found(client, auth_header, app_fixture):
    """Export for a non-existent user_id returns 403 (ownership check runs first)."""
    # The route checks current_uid != user_id before user existence;
    # for user_id=99999 the auth user's id won't match, so 403 is returned.
    r = client.get("/gdpr/users/99999/export", headers=auth_header)
    assert r.status_code == 403


# ─── Delete tests ────────────────────────────────────────────────────────────


def test_delete_removes_user_and_all_data(client, auth_header, app_fixture):
    """DELETE /gdpr/users/<id> should permanently remove the user and all PII."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        user_id = user.id

    _seed_user_data(app_fixture, user_id)

    r = client.delete(
        f"/gdpr/users/{user_id}",
        json={"confirm": True},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert "permanently deleted" in r.get_json()["message"].lower()

    # Verify all data is gone
    with app_fixture.app_context():
        assert db.session.get(User, user_id) is None
        assert db.session.query(Category).filter_by(user_id=user_id).count() == 0
        assert db.session.query(Expense).filter_by(user_id=user_id).count() == 0
        assert (
            db.session.query(RecurringExpense).filter_by(user_id=user_id).count() == 0
        )
        assert db.session.query(Bill).filter_by(user_id=user_id).count() == 0
        assert db.session.query(Reminder).filter_by(user_id=user_id).count() == 0
        assert db.session.query(UserSubscription).filter_by(user_id=user_id).count() == 0
        # Ad impressions: user_id set to NULL, not deleted
        assert (
            db.session.query(AdImpression).filter_by(user_id=user_id).count() == 0
        )


def test_delete_creates_audit_log_that_survives(client, auth_header, app_fixture):
    """Deletion should log a GDPR_DATA_DELETE audit entry that persists after user removal."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        user_id = user.id

    r = client.delete(
        f"/gdpr/users/{user_id}",
        json={"confirm": True},
        headers=auth_header,
    )
    assert r.status_code == 200

    with app_fixture.app_context():
        logs = db.session.query(AuditLog).filter_by(action="GDPR_DATA_DELETE").all()
        assert len(logs) >= 1
        # user_id should be NULL (anonymised) after user deletion
        for log in logs:
            assert log.user_id is None


def test_delete_requires_confirmation(client, auth_header, app_fixture):
    """Deletion without confirm=true should return 400."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        user_id = user.id

    # No body at all
    r = client.delete(f"/gdpr/users/{user_id}", headers=auth_header)
    assert r.status_code == 400

    # Body with confirm=false
    r = client.delete(
        f"/gdpr/users/{user_id}",
        json={"confirm": False},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_delete_forbidden_for_other_user(client, app_fixture):
    """A user cannot delete another user."""
    _, auth1 = _register_and_login(client, app_fixture, "deleter1@gdpr.test", "pass1")
    uid2, _ = _register_and_login(client, app_fixture, "deleter2@gdpr.test", "pass2")

    r = client.delete(
        f"/gdpr/users/{uid2}",
        json={"confirm": True},
        headers=auth1,
    )
    assert r.status_code == 403


def test_delete_requires_auth(client, app_fixture):
    """Unauthenticated deletion should be rejected."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        if user:
            user_id = user.id
        else:
            user_id = 1

    r = client.delete(f"/gdpr/users/{user_id}", json={"confirm": True})
    assert r.status_code in (401, 422)


def test_delete_user_not_found(client, auth_header, app_fixture):
    """Deleting a non-existent user_id returns 403 (ownership check runs first)."""
    r = client.delete(
        "/gdpr/users/99999",
        json={"confirm": True},
        headers=auth_header,
    )
    assert r.status_code == 403


def test_ad_impressions_anonymised_on_delete(client, auth_header, app_fixture):
    """Ad impressions should have user_id set to NULL (not deleted) on user deletion."""
    with app_fixture.app_context():
        user = db.session.query(User).first()
        user_id = user.id
        ad = AdImpression(user_id=user_id, placement="banner")
        db.session.add(ad)
        db.session.commit()
        ad_id = ad.id

    r = client.delete(
        f"/gdpr/users/{user_id}",
        json={"confirm": True},
        headers=auth_header,
    )
    assert r.status_code == 200

    with app_fixture.app_context():
        ad_check = db.session.get(AdImpression, ad_id)
        assert ad_check is not None
        assert ad_check.user_id is None
