from datetime import datetime


def test_create_delivery_tracks_status(app_fixture):
    from app.extensions import db
    from app.models import Reminder, User
    from app.services.reminder_tracking import create_delivery

    with app_fixture.app_context():
        user = User(email="tracking@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        reminder = Reminder(
            user_id=user.id, message="Test", send_at=datetime.utcnow(),
        )
        db.session.add(reminder)
        db.session.commit()

        delivery = create_delivery(reminder)
        assert delivery.id is not None
        assert delivery.status.value == "PENDING"
        assert delivery.attempt_count == 0


def test_delivery_metrics_endpoint(client, auth_header):
    r = client.get("/reminders/delivery-metrics", headers=auth_header)
    assert r.status_code == 200
    metrics = r.get_json()
    assert "total" in metrics
    assert "by_status" in metrics
    assert "by_channel" in metrics
    assert "pending_retries" in metrics


def test_list_deliveries_endpoint(client, auth_header):
    r = client.get("/reminders/deliveries", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_retry_failed_deliveries_endpoint(client, auth_header):
    r = client.post("/reminders/retry-failed", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "retried" in data


def test_send_single_nonexistent_reminder_returns_404(client, auth_header):
    r = client.post("/reminders/send/99999", headers=auth_header)
    assert r.status_code == 404


def test_record_click_endpoint(client, auth_header):
    r = client.get("/reminders", headers=auth_header)
    reminders = r.get_json()
    if reminders:
        reminder_id = reminders[0]["id"]
        r = client.post(f"/reminders/deliveries/{reminder_id}/click", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["message"] == "clicked"
