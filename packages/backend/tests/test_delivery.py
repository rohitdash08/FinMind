from datetime import datetime, timedelta
from app.extensions import db
from app.models import Reminder, ReminderDelivery, ReminderDeliveryStatus
from app.services.delivery import delivery_tracker


def _create_reminder(client, auth_header, channel="email"):
  """Helper to create a reminder and return its ID."""
  r = client.post(
    "/reminders",
    json={
      "message": "Test reminder",
      "send_at": (datetime.utcnow() + timedelta(days=1)).isoformat(),
      "channel": channel,
    },
    headers=auth_header,
  )
  return r.get_json()["id"]


def test_record_delivery_attempt_pending(client, auth_header, app_fixture):
  reminder_id = _create_reminder(client, auth_header)
  with app_fixture.app_context():
    delivery = delivery_tracker.record_attempt(reminder_id, "email", "pending")
    assert delivery.reminder_id == reminder_id
    assert delivery.status == "pending"
    assert delivery.channel == "email"
    assert delivery.attempts == 1
    assert delivery.last_error is None
    assert delivery.delivered_at is None


def test_record_delivery_attempt_sent(client, auth_header, app_fixture):
  reminder_id = _create_reminder(client, auth_header, channel="whatsapp")
  with app_fixture.app_context():
    delivery = delivery_tracker.record_attempt(reminder_id, "whatsapp", "sent")
    assert delivery.status == "sent"
    assert delivery.attempts == 1


def test_record_delivery_attempt_delivered(client, auth_header, app_fixture):
  reminder_id = _create_reminder(client, auth_header)
  with app_fixture.app_context():
    delivery = delivery_tracker.record_attempt(reminder_id, "email", "delivered")
    assert delivery.status == "delivered"
    assert delivery.delivered_at is not None


def test_record_delivery_attempt_failed_with_error(client, auth_header, app_fixture):
  reminder_id = _create_reminder(client, auth_header)
  with app_fixture.app_context():
    delivery = delivery_tracker.record_attempt(reminder_id, "email", "failed", error="SMTP connection refused")
    assert delivery.status == "failed"
    assert delivery.last_error == "SMTP connection refused"


def test_record_multiple_attempts(client, auth_header, app_fixture):
  reminder_id = _create_reminder(client, auth_header)
  with app_fixture.app_context():
    delivery_tracker.record_attempt(reminder_id, "email", "failed", error="timeout")
    delivery = delivery_tracker.record_attempt(reminder_id, "email", "delivered")
    assert delivery.attempts == 2
    assert delivery.status == "delivered"
    assert delivery.delivered_at is not None


def test_get_delivery_stats_empty(client, auth_header, app_fixture):
  with app_fixture.app_context():
    stats = delivery_tracker.get_delivery_stats(days=30)
    assert stats["total"] == 0
    assert stats["delivered"] == 0
    assert stats["failed"] == 0
    assert stats["success_rate"] == 0
    assert stats["avg_attempts"] == 0


def test_get_delivery_stats(client, auth_header, app_fixture):
  reminder1 = _create_reminder(client, auth_header, channel="email")
  reminder2 = _create_reminder(client, auth_header, channel="email")
  reminder3 = _create_reminder(client, auth_header, channel="whatsapp")

  with app_fixture.app_context():
    delivery_tracker.record_attempt(reminder1, "email", "delivered")
    delivery_tracker.record_attempt(reminder2, "email", "failed", error="bounce")
    delivery_tracker.record_attempt(reminder3, "whatsapp", "bounced", error="invalid number")

    stats = delivery_tracker.get_delivery_stats(days=30)
    assert stats["total"] == 3
    assert stats["delivered"] == 1
    assert stats["failed"] == 2
    assert abs(stats["success_rate"] - 33.33) < 0.01
    assert stats["avg_attempts"] == 1.0


def test_get_delivery_stats_with_user_filter(client, auth_header, app_fixture):
  reminder_id = _create_reminder(client, auth_header)
  with app_fixture.app_context():
    from flask_jwt_extended import get_jwt_identity
    delivery_tracker.record_attempt(reminder_id, "email", "delivered")

    # Get the user id from the auth flow
    from app.models import Reminder
    reminder = db.session.get(Reminder, reminder_id)
    uid = reminder.user_id

    stats = delivery_tracker.get_delivery_stats(user_id=uid, days=30)
    assert stats["total"] == 1
    assert stats["delivered"] == 1


def test_get_channel_stats(client, auth_header, app_fixture):
  reminder1 = _create_reminder(client, auth_header, channel="email")
  reminder2 = _create_reminder(client, auth_header, channel="email")
  reminder3 = _create_reminder(client, auth_header, channel="whatsapp")

  with app_fixture.app_context():
    delivery_tracker.record_attempt(reminder1, "email", "delivered")
    delivery_tracker.record_attempt(reminder2, "email", "failed", error="bounce")
    delivery_tracker.record_attempt(reminder3, "whatsapp", "delivered")

    stats = delivery_tracker.get_channel_stats(days=30)
    assert "email" in stats
    assert "whatsapp" in stats
    assert stats["email"]["total"] == 2
    assert stats["email"]["delivered"] == 1
    assert stats["email"]["failed"] == 1
    assert stats["whatsapp"]["total"] == 1
    assert stats["whatsapp"]["delivered"] == 1
    assert stats["whatsapp"]["failed"] == 0


def test_delivery_stats_endpoint(client, auth_header):
  r = client.get("/delivery/stats", headers=auth_header)
  assert r.status_code == 200
  data = r.get_json()
  assert "total" in data
  assert "delivered" in data
  assert "failed" in data
  assert "success_rate" in data
  assert "avg_attempts" in data


def test_delivery_stats_endpoint_with_days(client, auth_header):
  r = client.get("/delivery/stats?days=7", headers=auth_header)
  assert r.status_code == 200


def test_channel_stats_endpoint(client, auth_header):
  r = client.get("/delivery/stats/channels", headers=auth_header)
  assert r.status_code == 200
  data = r.get_json()
  assert isinstance(data, dict)


def test_delivery_history_endpoint_empty(client, auth_header):
  r = client.get("/delivery/history", headers=auth_header)
  assert r.status_code == 200
  data = r.get_json()
  assert data["total"] == 0
  assert data["items"] == []
  assert data["page"] == 1
  assert data["page_size"] == 20


def test_delivery_history_with_pagination(client, auth_header, app_fixture):
  # Create multiple reminders and deliveries
  reminder_ids = []
  for i in range(5):
    rid = _create_reminder(client, auth_header, channel="email")
    reminder_ids.append(rid)

  with app_fixture.app_context():
    for rid in reminder_ids:
      delivery_tracker.record_attempt(rid, "email", "delivered")

  r = client.get("/delivery/history?page=1&page_size=2", headers=auth_header)
  assert r.status_code == 200
  data = r.get_json()
  assert data["total"] == 5
  assert len(data["items"]) == 2
  assert data["page"] == 1
  assert data["page_size"] == 2

  r = client.get("/delivery/history?page=3&page_size=2", headers=auth_header)
  data = r.get_json()
  assert len(data["items"]) == 1


def test_delivery_history_item_fields(client, auth_header, app_fixture):
  reminder_id = _create_reminder(client, auth_header, channel="email")
  with app_fixture.app_context():
    delivery_tracker.record_attempt(reminder_id, "email", "delivered")

  r = client.get("/delivery/history", headers=auth_header)
  data = r.get_json()
  assert data["total"] == 1
  item = data["items"][0]
  assert "id" in item
  assert "reminder_id" in item
  assert "status" in item
  assert "channel" in item
  assert "attempts" in item
  assert "delivered_at" in item
  assert "created_at" in item
  assert "updated_at" in item
  assert item["status"] == "delivered"
  assert item["channel"] == "email"
  assert item["attempts"] == 1
  assert item["delivered_at"] is not None


def test_delivery_history_requires_auth(client):
  r = client.get("/delivery/history")
  assert r.status_code == 401


def test_delivery_stats_requires_auth(client):
  r = client.get("/delivery/stats")
  assert r.status_code == 401


def test_channel_stats_requires_auth(client):
  r = client.get("/delivery/stats/channels")
  assert r.status_code == 401
