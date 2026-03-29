"""Tests for job alert callbacks."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.job_execution import JobExecution, JobStatus
from app.services.job_alerts import (
    email_alert,
    log_alert,
    webhook_alert,
)


def _make_execution(status=JobStatus.DEAD, **overrides):
    """Create a mock-like JobExecution without DB."""
    defaults = dict(
        id=1,
        job_id="test_alert_123",
        job_name="test_job",
        status=status,
        attempt=3,
        max_retries=3,
        error_message="something broke",
        error_traceback="Traceback ...",
    )
    defaults.update(overrides)
    e = MagicMock(spec=JobExecution)
    for k, v in defaults.items():
        setattr(e, k, v)
    return e


class TestLogAlert:
    def test_logs_dead_as_error(self):
        execution = _make_execution(status=JobStatus.DEAD)
        with patch("app.services.job_alerts.logger") as mock_logger:
            log_alert(execution)
            mock_logger.log.assert_called_once()
            # First arg is log level (ERROR = 40)
            assert mock_logger.log.call_args[0][0] == 40

    def test_logs_retrying_as_warning(self):
        execution = _make_execution(status=JobStatus.RETRYING)
        with patch("app.services.job_alerts.logger") as mock_logger:
            log_alert(execution)
            assert mock_logger.log.call_args[0][0] == 30  # WARNING


class TestWebhookAlert:
    @patch.dict("os.environ", {"JOB_ALERT_WEBHOOK_URL": "https://hooks.example.com/job"})
    @patch("app.services.job_alerts.requests.post")
    def test_sends_webhook(self, mock_post):
        execution = _make_execution()
        webhook_alert(execution)
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["status"] == "DEAD"
        assert payload["job_name"] == "test_job"

    @patch.dict("os.environ", {}, clear=True)
    def test_skips_without_url(self):
        execution = _make_execution()
        # Should not raise
        webhook_alert(execution)


class TestEmailAlert:
    def test_skips_non_dead(self):
        execution = _make_execution(status=JobStatus.RETRYING)
        # Should not raise or send
        email_alert(execution)

    @patch("app.services.job_alerts.send_email")
    def test_sends_for_dead(self, mock_send):
        execution = _make_execution(status=JobStatus.DEAD)
        with patch("app.services.job_alerts.Settings") as MockSettings:
            MockSettings.return_value.smtp_url = "smtp+ssl://u:p@h:465"
            MockSettings.return_value.email_from = "admin@test.com"
            email_alert(execution)
            mock_send.assert_called_once()
