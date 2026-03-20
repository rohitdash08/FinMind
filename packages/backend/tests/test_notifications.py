from datetime import date, timedelta
from app.models import Notification, NotificationType, NotificationPriority, Bill, BillCadence
from app.extensions import db
from app.services.notifications import (
    generate_bill_due_notifications,
    generate_budget_exceeded_notification,
    generate_weekly_summary,
)
from decimal import Decimal


def _create_notification(app, uid, **kwargs):
    defaults = {
        "user_id": uid,
        "type": NotificationType.BILL_DUE.value,
        "priority": NotificationPriority.HIGH.value,
        "group": "bills",
        "message": "Test notification",
        "read": False,
    }
    defaults.update(kwargs)
    with app.app_context():
        n = Notification(**defaults)
        db.session.add(n)
        db.session.commit()
        return n.id


def test_list_notifications_empty(client, auth_header):
    r = client.get("/notifications", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["unread_count"] == 0
    assert data["notifications"] == {}


def test_list_notifications_grouped(client, auth_header, app_fixture):
    from flask_jwt_extended import decode_token

    with app_fixture.app_context():
        token = auth_header["Authorization"].split(" ")[1]
        uid = int(decode_token(token)["sub"])

    _create_notification(
        app_fixture,
        uid,
        type=NotificationType.BILL_DUE.value,
        group="bills",
        message="Bill A due",
    )
    _create_notification(
        app_fixture,
        uid,
        type=NotificationType.BUDGET_EXCEEDED.value,
        group="budgets",
        message="Budget exceeded",
    )

    r = client.get("/notifications", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["unread_count"] == 2
    assert "bills" in data["notifications"]
    assert "budgets" in data["notifications"]
    assert len(data["notifications"]["bills"]) == 1
    assert len(data["notifications"]["budgets"]) == 1


def test_mark_notification_read(client, auth_header, app_fixture):
    from flask_jwt_extended import decode_token

    with app_fixture.app_context():
        token = auth_header["Authorization"].split(" ")[1]
        uid = int(decode_token(token)["sub"])

    nid = _create_notification(app_fixture, uid)

    r = client.patch(f"/notifications/{nid}/read", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "marked as read"

    r = client.get("/notifications", headers=auth_header)
    assert r.get_json()["unread_count"] == 0


def test_mark_notification_read_not_found(client, auth_header):
    r = client.patch("/notifications/99999/read", headers=auth_header)
    assert r.status_code == 404


def test_mark_all_read(client, auth_header, app_fixture):
    from flask_jwt_extended import decode_token

    with app_fixture.app_context():
        token = auth_header["Authorization"].split(" ")[1]
        uid = int(decode_token(token)["sub"])

    _create_notification(app_fixture, uid, message="A")
    _create_notification(app_fixture, uid, message="B")

    r = client.post("/notifications/mark-all-read", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["count"] == 2

    r = client.get("/notifications", headers=auth_header)
    assert r.get_json()["unread_count"] == 0


def test_generate_bill_due_notifications(app_fixture, auth_header):
    from flask_jwt_extended import decode_token

    with app_fixture.app_context():
        token = auth_header["Authorization"].split(" ")[1]
        uid = int(decode_token(token)["sub"])

        bill = Bill(
            user_id=uid,
            name="Internet",
            amount=49.99,
            currency="USD",
            next_due_date=date.today() + timedelta(days=1),
            cadence=BillCadence.MONTHLY,
        )
        db.session.add(bill)
        db.session.commit()

        count = generate_bill_due_notifications(uid)
        assert count == 1

        # Running again should not duplicate
        count2 = generate_bill_due_notifications(uid)
        assert count2 == 0


def test_generate_budget_exceeded_notification(app_fixture, auth_header):
    from flask_jwt_extended import decode_token

    with app_fixture.app_context():
        token = auth_header["Authorization"].split(" ")[1]
        uid = int(decode_token(token)["sub"])

        n = generate_budget_exceeded_notification(uid, "Food", Decimal("150.00"), Decimal("100.00"))
        assert n.priority == NotificationPriority.CRITICAL.value
        assert "Food" in n.message


def test_generate_weekly_summary(app_fixture, auth_header):
    from flask_jwt_extended import decode_token

    with app_fixture.app_context():
        token = auth_header["Authorization"].split(" ")[1]
        uid = int(decode_token(token)["sub"])

        n = generate_weekly_summary(uid, Decimal("500.00"), 12)
        assert n.priority == NotificationPriority.LOW.value
        assert "12 transactions" in n.message
