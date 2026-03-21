"""
Tests for Celery task retry and monitoring functionality.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.celery_config import celery_app
from app.tasks.reminders import send_reminder_task, _send_to_dead_letter, process_due_reminders
from app.tasks.monitoring import task_monitor, get_task_statistics
from app.models import Reminder, NotificationLog, User


class TestSendReminderTask:
    """Test suite for send_reminder_task."""
    
    @patch("app.tasks.reminders.redis_client")
    @patch("app.tasks.reminders.send_email")
    def test_send_reminder_success_email(self, mock_send_email, mock_redis, app, db_session):
        """Test successful email reminder sending."""
        mock_send_email.return_value = True
        mock_redis.get.return_value = None
        
        # Create test user and reminder
        user = User(email="test@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        reminder = Reminder(
            user_id=user.id,
            message="Test reminder",
            send_at=datetime.now(timezone.utc),
            channel="test@example.com",
            is_sent=False
        )
        db_session.add(reminder)
        db_session.commit()
        
        # Execute task
        result = send_reminder_task.run(reminder.id)
        
        assert result["status"] == "success"
        assert result["channel"] == "email"
        mock_send_email.assert_called_once()
        mock_redis.setex.assert_called_once()
    
    @patch("app.tasks.reminders.redis_client")
    @patch("app.tasks.reminders.send_email")
    def test_send_reminder_already_sent(self, mock_send_email, mock_redis, app, db_session):
        """Test idempotency - reminder already sent."""
        mock_redis.get.return_value = b"1"
        
        user = User(email="test@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        reminder = Reminder(
            user_id=user.id,
            message="Test reminder",
            send_at=datetime.now(timezone.utc),
            channel="test@example.com",
            is_sent=False
        )
        db_session.add(reminder)
        db_session.commit()
        
        result = send_reminder_task.run(reminder.id)
        
        assert result["status"] == "skipped"
        assert result["reason"] == "already_sent"
        mock_send_email.assert_not_called()
    
    @patch("app.tasks.reminders.redis_client")
    @patch("app.tasks.reminders.send_email")
    def test_send_reminder_not_found(self, mock_send_email, mock_redis, app, db_session):
        """Test reminder not found."""
        result = send_reminder_task.run(99999)
        
        assert result["status"] == "error"
        assert result["reason"] == "reminder_not_found"
    
    @patch("app.tasks.reminders.redis_client")
    @patch("app.tasks.reminders.send_email")
    def test_send_reminder_failure_triggers_retry(self, mock_send_email, mock_redis, app, db_session):
        """Test that failed delivery triggers retry."""
        mock_send_email.return_value = False
        mock_redis.get.return_value = None
        
        user = User(email="test@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        reminder = Reminder(
            user_id=user.id,
            message="Test reminder",
            send_at=datetime.now(timezone.utc),
            channel="test@example.com",
            is_sent=False
        )
        db_session.add(reminder)
        db_session.commit()
        
        # Mock the task's retry method
        with patch.object(send_reminder_task, "retry") as mock_retry:
            mock_retry.side_effect = Exception("Retry triggered")
            
            with pytest.raises(Exception, match="Retry triggered"):
                send_reminder_task.run(reminder.id)
            
            mock_retry.assert_called_once()


class TestDeadLetterQueue:
    """Test suite for dead letter queue functionality."""
    
    @patch("app.tasks.reminders.redis_client")
    def test_send_to_dead_letter(self, mock_redis):
        """Test dead letter queue insertion."""
        import json
        
        _send_to_dead_letter(123, "test_reason", "task_123")
        
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "dead_letter:reminders:123"
        
        # Verify JSON structure
        data = json.loads(call_args[0][1])
        assert data["reminder_id"] == 123
        assert data["reason"] == "test_reason"
        assert data["original_task_id"] == "task_123"


class TestProcessDueReminders:
    """Test suite for process_due_reminders."""
    
    @patch("app.tasks.reminders.send_reminder_task")
    def test_process_due_reminders_schedules_tasks(self, mock_task, app, db_session):
        """Test that due reminders are scheduled."""
        mock_task.apply_async = Mock()
        
        user = User(email="test@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        # Create due reminders
        for i in range(3):
            reminder = Reminder(
                user_id=user.id,
                message=f"Reminder {i}",
                send_at=datetime.now(timezone.utc) - timedelta(hours=1),
                channel="test@example.com",
                is_sent=False
            )
            db_session.add(reminder)
        db_session.commit()
        
        result = process_due_reminders.run()
        
        assert result["scheduled"] == 3
        assert result["errors"] == 0
        assert mock_task.apply_async.call_count == 3


class TestTaskMonitoring:
    """Test suite for task monitoring."""
    
    @patch("app.tasks.monitoring.redis_client")
    def test_get_task_statistics(self, mock_redis):
        """Test task statistics collection."""
        mock_redis.keys.side_effect = [
            [b"task:active:1"],
            [b"task:completed:1", b"task:completed:2"],
            [b"task:failed:1"],
            [b"task:retry:1"],
            [b"dead_letter:1"],
        ]
        
        stats = get_task_statistics()
        
        assert stats["active_tasks"] == 1
        assert stats["completed_24h"] == 2
        assert stats["failed_7d"] == 1
        assert stats["retries_24h"] == 1
        assert stats["dead_letter"] == 1
        assert "timestamp" in stats


class TestCeleryConfiguration:
    """Test suite for Celery configuration."""
    
    def test_celery_app_exists(self):
        """Test that Celery app is properly configured."""
        assert celery_app is not None
        assert celery_app.main == "finmind"
    
    def test_queues_configured(self):
        """Test that all required queues are configured."""
        queues = celery_app.conf.task_queues
        queue_names = [q.name for q in queues]
        
        assert "default" in queue_names
        assert "high_priority" in queue_names
        assert "low_priority" in queue_names
        assert "dead_letter" in queue_names
    
    def test_retry_configuration(self):
        """Test retry settings."""
        assert celery_app.conf.task_default_retry_delay == 60
        assert celery_app.conf.task_max_retries == 5
    
    def test_time_limits(self):
        """Test task time limits."""
        assert celery_app.conf.task_time_limit == 300
        assert celery_app.conf.task_soft_time_limit == 240
