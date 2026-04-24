from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import AuditLog, Bill, BillCadence, Category, Expense, Reminder, User


def _register_and_login(client, email="privacy@test.com"):
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_user_can_export_personal_data(client, app_fixture):
    auth = _register_and_login(client, "export@test.com")
    with app_fixture.app_context():
        user = User.query.filter_by(email="export@test.com").one()
        category = Category(user_id=user.id, name="Travel")
        db.session.add(category)
        db.session.flush()
        db.session.add(
            Expense(
                user_id=user.id,
                category_id=category.id,
                amount=12.50,
                currency="USD",
                notes="Airport coffee",
                spent_at=date.today(),
            )
        )
        db.session.add(
            Bill(
                user_id=user.id,
                name="Card",
                amount=25,
                currency="USD",
                next_due_date=date.today(),
                cadence=BillCadence.MONTHLY,
            )
        )
        db.session.commit()

    r = client.get("/auth/me/export", headers=auth)

    assert r.status_code == 200
    payload = r.get_json()
    assert payload["user"]["email"] == "export@test.com"
    assert payload["categories"][0]["name"] == "Travel"
    assert payload["expenses"][0]["notes"] == "Airport coffee"
    assert payload["bills"][0]["name"] == "Card"
    with app_fixture.app_context():
        assert AuditLog.query.filter_by(action="USER_DATA_EXPORTED").count() == 1


def test_user_can_irreversibly_delete_personal_data(client, app_fixture):
    auth = _register_and_login(client, "delete@test.com")
    with app_fixture.app_context():
        user = User.query.filter_by(email="delete@test.com").one()
        bill = Bill(
            user_id=user.id,
            name="Internet",
            amount=30,
            currency="USD",
            next_due_date=date.today(),
            cadence=BillCadence.MONTHLY,
        )
        db.session.add(bill)
        db.session.flush()
        db.session.add(
            Reminder(
                user_id=user.id,
                bill_id=bill.id,
                message="pay internet",
                send_at=datetime.utcnow() + timedelta(days=1),
            )
        )
        db.session.commit()
        uid = user.id

    r = client.delete("/auth/me", headers=auth)

    assert r.status_code == 200
    with app_fixture.app_context():
        assert db.session.get(User, uid) is None
        assert Bill.query.filter_by(user_id=uid).count() == 0
        assert Reminder.query.filter_by(user_id=uid).count() == 0
        assert (
            AuditLog.query.filter(AuditLog.action == f"USER_DATA_DELETED:{uid}").count()
            == 1
        )
