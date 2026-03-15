"""Tests for reminder reliability tracking and delivery metrics."""

import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import Reminder, ReminderDelivery


def _create_reminder(user_id=1, message="Test reminder"):
    """Helper to create a test reminder."""
    r = Reminder(
        user_id=user_id,
        message=message,
        send_at=datetime.utcnow() + timedelta(hours=1),
        channel="email",
    )
    db.session.add(r)
    db.session.commit()
    return r


# ═══════════════════════════════════════════════════════════════════
# Service unit tests
# ═══════════════════════════════════════════════════════════════════


class TestRecordDelivery:
    """Test delivery recording functions."""

    def test_record_attempt(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt

        with client.application.app_context():
            reminder = _create_reminder()
            result = record_delivery_attempt(reminder.id, 1)

        assert result["status"] == "pending"
        assert result["attempt_number"] == 1
        assert result["channel"] == "email"

    def test_record_multiple_attempts(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt

        with client.application.app_context():
            reminder = _create_reminder()
            r1 = record_delivery_attempt(reminder.id, 1, channel="email")
            r2 = record_delivery_attempt(reminder.id, 1, channel="email")

        assert r1["attempt_number"] == 1
        assert r2["attempt_number"] == 2

    def test_record_different_channels(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt

        with client.application.app_context():
            reminder = _create_reminder()
            r1 = record_delivery_attempt(reminder.id, 1, channel="email")
            r2 = record_delivery_attempt(reminder.id, 1, channel="push")

        assert r1["channel"] == "email"
        assert r2["channel"] == "push"
        assert r2["attempt_number"] == 1  # New channel starts at 1


class TestStatusTransitions:
    """Test status marking functions."""

    def test_mark_sent(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, mark_sent

        with client.application.app_context():
            reminder = _create_reminder()
            r = record_delivery_attempt(reminder.id, 1)
            result = mark_sent(r["id"], "200")

        assert result["status"] == "sent"
        assert result["sent_at"] is not None
        assert result["response_code"] == "200"

    def test_mark_delivered(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, mark_delivered

        with client.application.app_context():
            reminder = _create_reminder()
            r = record_delivery_attempt(reminder.id, 1)
            result = mark_delivered(r["id"], latency_ms=150)

        assert result["status"] == "delivered"
        assert result["delivered_at"] is not None
        assert result["latency_ms"] == 150

    def test_mark_failed(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, mark_failed

        with client.application.app_context():
            reminder = _create_reminder()
            r = record_delivery_attempt(reminder.id, 1)
            result = mark_failed(r["id"], reason="Timeout", response_code="504")

        assert result["status"] == "failed"
        assert result["failure_reason"] == "Timeout"
        assert result["response_code"] == "504"

    def test_mark_bounced(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, mark_bounced

        with client.application.app_context():
            reminder = _create_reminder()
            r = record_delivery_attempt(reminder.id, 1)
            result = mark_bounced(r["id"], reason="Mailbox full")

        assert result["status"] == "bounced"
        assert result["failure_reason"] == "Mailbox full"

    def test_mark_nonexistent_returns_none(self, client, auth_header):
        from app.services.reminder_tracking import mark_sent, mark_delivered, mark_failed, mark_bounced

        with client.application.app_context():
            assert mark_sent(9999) is None
            assert mark_delivered(9999) is None
            assert mark_failed(9999) is None
            assert mark_bounced(9999) is None


class TestEngagementTracking:
    """Test open/click tracking."""

    def test_record_opened(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, record_opened

        with client.application.app_context():
            reminder = _create_reminder()
            r = record_delivery_attempt(reminder.id, 1)
            result = record_opened(r["id"])

        assert result["opened"] is True
        assert result["opened_at"] is not None

    def test_record_clicked(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, record_clicked

        with client.application.app_context():
            reminder = _create_reminder()
            r = record_delivery_attempt(reminder.id, 1)
            result = record_clicked(r["id"])

        assert result["clicked"] is True
        assert result["opened"] is True  # Click implies open

    def test_engagement_nonexistent(self, client, auth_header):
        from app.services.reminder_tracking import record_opened, record_clicked

        with client.application.app_context():
            assert record_opened(9999) is None
            assert record_clicked(9999) is None


class TestDeliveryHistory:
    """Test query functions."""

    def test_empty_history(self, client, auth_header):
        from app.services.reminder_tracking import get_delivery_history

        with client.application.app_context():
            result = get_delivery_history(1)

        assert result == []

    def test_history_returns_records(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, get_delivery_history

        with client.application.app_context():
            reminder = _create_reminder()
            record_delivery_attempt(reminder.id, 1, channel="email")
            record_delivery_attempt(reminder.id, 1, channel="push")
            result = get_delivery_history(1)

        assert len(result) == 2

    def test_history_filter_by_channel(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, get_delivery_history

        with client.application.app_context():
            reminder = _create_reminder()
            record_delivery_attempt(reminder.id, 1, channel="email")
            record_delivery_attempt(reminder.id, 1, channel="push")
            result = get_delivery_history(1, channel="push")

        assert len(result) == 1
        assert result[0]["channel"] == "push"

    def test_history_filter_by_status(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, mark_delivered, get_delivery_history

        with client.application.app_context():
            reminder = _create_reminder()
            r1 = record_delivery_attempt(reminder.id, 1)
            r2 = record_delivery_attempt(reminder.id, 1)
            mark_delivered(r1["id"])
            result = get_delivery_history(1, status="delivered")

        assert len(result) == 1

    def test_history_limit(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, get_delivery_history

        with client.application.app_context():
            reminder = _create_reminder()
            for _ in range(5):
                record_delivery_attempt(reminder.id, 1)
            result = get_delivery_history(1, limit=3)

        assert len(result) == 3

    def test_reminder_deliveries(self, client, auth_header):
        from app.services.reminder_tracking import record_delivery_attempt, get_reminder_deliveries

        with client.application.app_context():
            reminder = _create_reminder()
            record_delivery_attempt(reminder.id, 1, channel="email")
            record_delivery_attempt(reminder.id, 1, channel="push")
            result = get_reminder_deliveries(reminder.id)

        assert len(result) == 2


class TestReliabilityMetrics:
    """Test reliability metrics calculation."""

    def test_empty_metrics(self, client, auth_header):
        from app.services.reminder_tracking import get_reliability_metrics

        with client.application.app_context():
            metrics = get_reliability_metrics(1)

        assert metrics["total_attempts"] == 0
        assert metrics["delivery_rate"] == 0.0

    def test_metrics_with_data(self, client, auth_header):
        from app.services.reminder_tracking import (
            record_delivery_attempt, mark_delivered, mark_failed,
            record_opened, get_reliability_metrics,
        )

        with client.application.app_context():
            reminder = _create_reminder()
            r1 = record_delivery_attempt(reminder.id, 1)
            r2 = record_delivery_attempt(reminder.id, 1)
            r3 = record_delivery_attempt(reminder.id, 1)
            mark_delivered(r1["id"], latency_ms=100)
            mark_delivered(r2["id"], latency_ms=200)
            mark_failed(r3["id"], reason="error")
            record_opened(r1["id"])

            metrics = get_reliability_metrics(1)

        assert metrics["total_attempts"] == 3
        assert metrics["delivery_rate"] == round(2 / 3, 3)
        assert metrics["failure_rate"] == round(1 / 3, 3)
        assert metrics["open_rate"] == 0.5
        assert metrics["avg_latency_ms"] == 150

    def test_channel_performance(self, client, auth_header):
        from app.services.reminder_tracking import (
            record_delivery_attempt, mark_delivered, get_channel_performance,
        )

        with client.application.app_context():
            reminder = _create_reminder()
            r1 = record_delivery_attempt(reminder.id, 1, channel="email")
            r2 = record_delivery_attempt(reminder.id, 1, channel="push")
            mark_delivered(r1["id"])
            mark_delivered(r2["id"])

            perf = get_channel_performance(1)

        assert len(perf) == 2
        assert all(p["delivery_rate"] == 1.0 for p in perf)


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestTrackingRoutes:
    """Integration tests for /tracking/* endpoints."""

    def _create_reminder_via_db(self, client):
        """Helper to create reminder in app context."""
        with client.application.app_context():
            r = _create_reminder()
            return r.id

    # ── POST /tracking/record ──
    def test_record_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        r = client.post("/tracking/record",
                        json={"reminder_id": rid, "channel": "email"},
                        headers=auth_header)
        assert r.status_code == 201
        assert r.get_json()["status"] == "pending"

    def test_record_missing_reminder_id(self, client, auth_header):
        r = client.post("/tracking/record", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_record_unauthorized(self, client):
        r = client.post("/tracking/record", json={"reminder_id": 1})
        assert r.status_code == 401

    # ── POST /tracking/<id>/sent ──
    def test_sent_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        cr = client.post("/tracking/record",
                         json={"reminder_id": rid},
                         headers=auth_header)
        did = cr.get_json()["id"]

        r = client.post(f"/tracking/{did}/sent", json={}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] == "sent"

    def test_sent_nonexistent(self, client, auth_header):
        r = client.post("/tracking/9999/sent", json={}, headers=auth_header)
        assert r.status_code == 404

    # ── POST /tracking/<id>/delivered ──
    def test_delivered_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        cr = client.post("/tracking/record",
                         json={"reminder_id": rid},
                         headers=auth_header)
        did = cr.get_json()["id"]

        r = client.post(f"/tracking/{did}/delivered",
                        json={"latency_ms": 250},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["latency_ms"] == 250

    # ── POST /tracking/<id>/failed ──
    def test_failed_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        cr = client.post("/tracking/record",
                         json={"reminder_id": rid},
                         headers=auth_header)
        did = cr.get_json()["id"]

        r = client.post(f"/tracking/{did}/failed",
                        json={"reason": "Network error"},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["failure_reason"] == "Network error"

    # ── POST /tracking/<id>/bounced ──
    def test_bounced_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        cr = client.post("/tracking/record",
                         json={"reminder_id": rid},
                         headers=auth_header)
        did = cr.get_json()["id"]

        r = client.post(f"/tracking/{did}/bounced",
                        json={"reason": "Mailbox full"},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] == "bounced"

    # ── POST /tracking/<id>/opened ──
    def test_opened_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        cr = client.post("/tracking/record",
                         json={"reminder_id": rid},
                         headers=auth_header)
        did = cr.get_json()["id"]

        r = client.post(f"/tracking/{did}/opened", json={}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["opened"] is True

    # ── POST /tracking/<id>/clicked ──
    def test_clicked_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        cr = client.post("/tracking/record",
                         json={"reminder_id": rid},
                         headers=auth_header)
        did = cr.get_json()["id"]

        r = client.post(f"/tracking/{did}/clicked", json={}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["clicked"] is True

    # ── GET /tracking/history ──
    def test_history_route(self, client, auth_header):
        r = client.get("/tracking/history", headers=auth_header)
        assert r.status_code == 200
        assert "deliveries" in r.get_json()

    def test_history_with_filters(self, client, auth_header):
        r = client.get("/tracking/history?channel=email&status=pending&limit=10",
                        headers=auth_header)
        assert r.status_code == 200

    # ── GET /tracking/reminder/<id> ──
    def test_reminder_deliveries_route(self, client, auth_header):
        rid = self._create_reminder_via_db(client)
        client.post("/tracking/record",
                    json={"reminder_id": rid},
                    headers=auth_header)

        r = client.get(f"/tracking/reminder/{rid}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] >= 1

    # ── GET /tracking/metrics ──
    def test_metrics_route(self, client, auth_header):
        r = client.get("/tracking/metrics", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "delivery_rate" in body
        assert "by_channel" in body

    def test_metrics_with_days(self, client, auth_header):
        r = client.get("/tracking/metrics?days=7", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["period_days"] == 7

    # ── GET /tracking/channels ──
    def test_channels_route(self, client, auth_header):
        r = client.get("/tracking/channels", headers=auth_header)
        assert r.status_code == 200
        assert "channels" in r.get_json()
