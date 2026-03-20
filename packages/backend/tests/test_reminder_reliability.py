"""
Tests for Reminder Reliability Tracking & Delivery Metrics (Issue #123)
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from app.services.reminder_reliability import ReminderReliabilityService
from app.models import ReminderDeliveryLog, Reminder


@pytest.fixture
def svc():
    return ReminderReliabilityService()


@pytest.fixture
def mock_db(monkeypatch):
    """Patch db.session for unit tests."""
    session = MagicMock()
    monkeypatch.setattr("app.services.reminder_reliability.db.session", session)
    monkeypatch.setattr("app.services.reminder_reliability.db.session", session)
    return session


def make_log(status="delivered", channel="email", latency_ms=120.0, error_code=None, retry_count=0):
    log = MagicMock(spec=ReminderDeliveryLog)
    log.status = status
    log.channel = channel
    log.latency_ms = latency_ms
    log.error_code = error_code
    log.retry_count = retry_count
    log.attempted_at = datetime.utcnow()
    log.reminder_id = 1
    log.user_id = 1
    return log


class TestGetDeliveryMetrics:
    def test_empty_returns_defaults(self, svc, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []
        result = svc.get_delivery_metrics(user_id=1)
        assert result["total_attempts"] == 0
        assert result["success_rate"] == 1.0
        assert result["failure_rate"] == 0.0

    def test_all_delivered(self, svc, mock_db):
        logs = [make_log(status="delivered", latency_ms=100.0) for _ in range(10)]
        mock_db.query.return_value.filter.return_value.all.return_value = logs
        result = svc.get_delivery_metrics(user_id=1)
        assert result["total_attempts"] == 10
        assert result["success_rate"] == 1.0
        assert result["failure_rate"] == 0.0

    def test_mixed_success_failure(self, svc, mock_db):
        logs = (
            [make_log(status="delivered", latency_ms=100.0) for _ in range(7)]
            + [make_log(status="failed", error_code="SMTP_TIMEOUT") for _ in range(3)]
        )
        mock_db.query.return_value.filter.return_value.all.return_value = logs
        result = svc.get_delivery_metrics(user_id=1)
        assert result["success_rate"] == pytest.approx(0.7, abs=0.01)
        assert result["failure_rate"] == pytest.approx(0.3, abs=0.01)
        assert result["error_breakdown"]["SMTP_TIMEOUT"] == 3

    def test_latency_calculation(self, svc, mock_db):
        latencies = [100.0, 200.0, 150.0, 300.0, 50.0]
        logs = [make_log(latency_ms=l) for l in latencies]
        mock_db.query.return_value.filter.return_value.all.return_value = logs
        result = svc.get_delivery_metrics(user_id=1)
        assert result["avg_latency_ms"] == pytest.approx(160.0, abs=1.0)
        assert result["p95_latency_ms"] is not None

    def test_channel_filter(self, svc, mock_db):
        logs = [make_log(channel="email") for _ in range(5)]
        query_mock = mock_db.query.return_value.filter.return_value
        query_mock.filter.return_value.all.return_value = logs
        result = svc.get_delivery_metrics(user_id=1, channel="email")
        assert "email" in result["channels"]

    def test_per_channel_breakdown(self, svc, mock_db):
        logs = (
            [make_log(channel="email", status="delivered") for _ in range(8)]
            + [make_log(channel="sms", status="failed", error_code="NO_CREDIT") for _ in range(2)]
        )
        mock_db.query.return_value.filter.return_value.all.return_value = logs
        result = svc.get_delivery_metrics(user_id=1)
        assert result["channels"]["email"]["delivered"] == 8
        assert result["channels"]["sms"]["failed"] == 2

    def test_period_days_in_result(self, svc, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []
        result = svc.get_delivery_metrics(user_id=1, days=90)
        assert result["period_days"] == 90


class TestGetReminderMetrics:
    def test_not_found(self, svc, mock_db):
        mock_db.get.return_value = None
        result = svc.get_reminder_metrics(user_id=1, reminder_id=999)
        assert result["error"] == "not_found"

    def test_wrong_user(self, svc, mock_db):
        reminder = MagicMock(spec=Reminder)
        reminder.user_id = 2  # different user
        mock_db.get.return_value = reminder
        result = svc.get_reminder_metrics(user_id=1, reminder_id=1)
        assert result["error"] == "not_found"

    def test_success(self, svc, mock_db):
        reminder = MagicMock(spec=Reminder)
        reminder.user_id = 1
        reminder.message = "Pay rent"
        reminder.channel = "email"
        mock_db.get.return_value = reminder
        logs = [
            make_log(status="delivered"),
            make_log(status="delivered"),
            make_log(status="failed", error_code="TIMEOUT"),
        ]
        mock_db.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = logs
        result = svc.get_reminder_metrics(user_id=1, reminder_id=1)
        assert result["total_attempts"] == 3
        assert result["delivered_count"] == 2
        assert result["failed_count"] == 1
        assert result["reliability_score"] == pytest.approx(2/3, abs=0.01)

    def test_empty_history(self, svc, mock_db):
        reminder = MagicMock(spec=Reminder)
        reminder.user_id = 1
        reminder.message = "Test"
        reminder.channel = "push"
        mock_db.get.return_value = reminder
        mock_db.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []
        result = svc.get_reminder_metrics(user_id=1, reminder_id=1)
        assert result["total_attempts"] == 0
        assert result["reliability_score"] == 1.0


class TestRecordDeliveryAttempt:
    def test_records_delivered(self, svc, mock_db):
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        log = svc.record_delivery_attempt(
            user_id=1, reminder_id=1, channel="email",
            status="delivered", latency_ms=95.0
        )
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_records_failure(self, svc, mock_db):
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        log = svc.record_delivery_attempt(
            user_id=1, reminder_id=1, channel="sms",
            status="failed", error_code="CARRIER_ERROR", retry_count=2
        )
        mock_db.add.assert_called_once()


class TestGetFailedReminders:
    def test_returns_unique_reminders(self, svc, mock_db):
        logs = [
            make_log(status="failed", error_code="TIMEOUT"),
            make_log(status="failed", error_code="TIMEOUT"),
        ]
        logs[0].reminder_id = 1
        logs[1].reminder_id = 1  # same reminder, duplicate
        mock_db.query.return_value.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = logs
        result = svc.get_failed_reminders(user_id=1)
        assert len(result) == 1  # deduplicated

    def test_empty(self, svc, mock_db):
        mock_db.query.return_value.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        result = svc.get_failed_reminders(user_id=1)
        assert result == []
