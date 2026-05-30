def test_create_and_list_notifications(app_fixture):
    from app.extensions import db
    from app.models import Notification, NotificationPriority, User
    from app.services.notification_priority import create_notification, list_notifications

    with app_fixture.app_context():
        user = User(email="notif@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        n = create_notification(
            user_id=user.id, title="Test", body="Body",
            priority=NotificationPriority.HIGH, group_key="test:1",
        )
        assert n.id is not None
        assert n.priority == NotificationPriority.HIGH

        items = list_notifications(user.id)
        assert len(items) == 1
        assert items[0]["priority"] == "HIGH"
        assert items[0]["group_key"] == "test:1"


def test_grouping_consolidates_duplicates(app_fixture):
    from app.extensions import db
    from app.models import User
    from app.services.notification_priority import create_notification, list_notifications

    with app_fixture.app_context():
        user = User(email="group@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        create_notification(
            user_id=user.id, title="Bill", body="Due soon",
            group_key="bill:1",
        )
        create_notification(
            user_id=user.id, title="Bill", body="Updated",
            group_key="bill:1",
        )

        items = list_notifications(user.id, unread_only=True)
        assert len(items) == 1
        assert items[0]["body"] == "Updated"


def test_mark_read_unread_count(client, auth_header):
    r = client.get("/notifications/unread-count", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "total" in data
    assert "by_priority" in data

    r = client.post("/notifications/mark-all-read", headers=auth_header)
    assert r.status_code == 200
    assert "marked" in r.get_json()

    r = client.get("/notifications/unread-count", headers=auth_header)
    assert r.get_json()["total"] == 0


def test_list_notifications_priority_filter(client, auth_header):
    r = client.get("/notifications?priority=HIGH", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)

    r = client.get("/notifications?unread_only=true", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_mark_notification_read(client, auth_header):
    r = client.get("/notifications", headers=auth_header)
    items = r.get_json()
    if items:
        nid = items[0]["id"]
        r = client.post(f"/notifications/{nid}/read", headers=auth_header)
        assert r.status_code == 200

        r = client.post("/notifications/99999/read", headers=auth_header)
        assert r.status_code == 404


def test_due_soon_batch_notifications(app_fixture):
    from app.extensions import db
    from app.models import Reminder, User
    from app.services.notification_priority import create_due_soon_notifications, list_notifications
    from datetime import datetime

    with app_fixture.app_context():
        user = User(email="due@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        reminders = [
            Reminder(user_id=user.id, message=f"Bill {i}", send_at=datetime.utcnow())
            for i in range(3)
        ]
        for r in reminders:
            db.session.add(r)
        db.session.commit()

        created = create_due_soon_notifications(user.id, reminders)
        assert len(created) == 1
        assert "3 Bills Due Soon" in created[0].title

        items = list_notifications(user.id)
        assert any("3 Bills Due Soon" in i["title"] for i in items)
