"""Tests for reminder reliability tracking & delivery metrics (issue #123)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# DB availability guard
# ---------------------------------------------------------------------------
try:
    from app.extensions import db  # noqa: F401
    _db_available = True
except Exception:
    _db_available = False

requires_db = pytest.mark.skipif(not _db_available, reason="Database not configured")


# ---------------------------------------------------------------------------
# Unit tests - no DB required
# ---------------------------------------------------------------------------

class TestReminderDeliveryStatusEnum:
    def test_all_statuses_valid(self):
        from app.models import ReminderDeliveryStatus
        assert ReminderDeliveryStatus.SENT.value == "SENT"
        assert ReminderDeliveryStatus.FAILED.value == "FAILED"
        assert ReminderDeliveryStatus.PENDING.value == "PENDING"
        assert ReminderDeliveryStatus.BOUNCED.value == "BOUNCED"

    def test_from_string(self):
        from app.models import ReminderDeliveryStatus
        s = ReminderDeliveryStatus("SENT")
        assert s == ReminderDeliveryStatus.SENT


class TestGetReliabilityMetricsMocked:
    def _make_log(self, status, channel="email", latency_ms=None):
        from app.models import ReminderDeliveryStatus
        log = MagicMock()
        log.status = ReminderDeliveryStatus(status)
        log.channel = channel
        log.latency_ms = latency_ms
        log.reminder_id = 1
        log.error_message = None
        log.attempted_at = datetime(2024, 4, 1, 12, 0, 0)
        return log

    def test_empty_logs(self):
        from app.services.reminder_reliability import get_reliability_metrics
        with patch("app.services.reminder_reliability.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            result = get_reliability_metrics(user_id=1, days=30)
        assert result["total_attempts"] == 0
        assert result["delivery_rate"] == 0.0
        assert result["failure_rate"] == 0.0
        assert result["avg_latency_ms"] is None

    def test_all_sent(self):
        from app.services.reminder_reliability import get_reliability_metrics
        logs = [self._make_log("SENT", latency_ms=120) for _ in range(5)]
        with patch("app.services.reminder_reliability.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = logs
            result = get_reliability_metrics(user_id=1, days=30)
        assert result["sent"] == 5
        assert result["failed"] == 0
        assert result["delivery_rate"] == 1.0
        assert result["avg_latency_ms"] == 120.0

    def test_mixed_statuses(self):
        from app.services.reminder_reliability import get_reliability_metrics
        logs = [
            self._make_log("SENT"),
            self._make_log("SENT"),
            self._make_log("FAILED"),
            self._make_log("BOUNCED"),
        ]
        with patch("app.services.reminder_reliability.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = logs
            result = get_reliability_metrics(user_id=1, days=30)
        assert result["total_attempts"] == 4
        assert result["sent"] == 2
        assert result["failed"] == 1
        assert result["bounced"] == 1
        assert result["delivery_rate"] == 0.5
        assert result["failure_rate"] == 0.5

    def test_channel_breakdown(self):
        from app.services.reminder_reliability import get_reliability_metrics
        logs = [
            self._make_log("SENT", channel="email"),
            self._make_log("FAILED", channel="email"),
            self._make_log("SENT", channel="whatsapp"),
        ]
        with patch("app.services.reminder_reliability.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = logs
            result = get_reliability_metrics(user_id=1)
        breakdown = {item["channel"]: item for item in result["channel_breakdown"]}
        assert "email" in breakdown
        assert "whatsapp" in breakdown
        assert breakdown["whatsapp"]["delivery_rate"] == 1.0
        assert breakdown["email"]["sent"] == 1
        assert breakdown["email"]["failed"] == 1

    def test_result_structure(self):
        from app.services.reminder_reliability import get_reliability_metrics
        with patch("app.services.reminder_reliability.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            result = get_reliability_metrics(user_id=1)
        expected_keys = {
            "period_days", "total_attempts", "sent", "failed", "bounced",
            "pending", "delivery_rate", "failure_rate", "avg_latency_ms",
            "channel_breakdown", "recent_failures",
        }
        assert expected_keys.issubset(result.keys())

    def test_recent_failures_limited(self):
        from app.services.reminder_reliability import get_reliability_metrics
        logs = [self._make_log("FAILED") for _ in range(15)]
        with patch("app.services.reminder_reliability.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = logs
            result = get_reliability_metrics(user_id=1)
        assert len(result["recent_failures"]) <= 10

    def test_period_days_in_result(self):
        from app.services.reminder_reliability import get_reliability_metrics
        with patch("app.services.reminder_reliability.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            result = get_reliability_metrics(user_id=1, days=7)
        assert result["period_days"] == 7
