"""Tests for reminder delivery tracking and reliability metrics."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models import Reminder, ReminderDelivery
from app.services.reminders import (
    deliver_reminder,
    get_delivery_metrics,
    get_failed_reminders,
    send_email,
    send_whatsapp,
    MAX_RETRY_ATTEMPTS,
)


class TestSendEmail:
    """Test email sending functionality."""
    
    @patch('app.services.reminders._settings')
    @patch('smtplib.SMTP_SSL')
    def test_send_email_success(self, mock_smtp, mock_settings):
        mock_settings.smtp_url = 'smtp+ssl://user:pass@smtp.gmail.com:465'
        mock_settings.email_from = 'test@example.com'
        
        success, error = send_email('to@example.com', 'Test Subject', 'Test Body')
        
        assert success is True
        assert error is None
    
    @patch('app.services.reminders._settings')
    def test_send_email_not_configured(self, mock_settings):
        mock_settings.smtp_url = None
        mock_settings.email_from = None
        
        success, error = send_email('to@example.com', 'Subject', 'Body')
        
        assert success is False
        assert 'not configured' in error.lower()
    
    @patch('app.services.reminders._settings')
    def test_send_email_invalid_url(self, mock_settings):
        mock_settings.smtp_url = 'invalid-url'
        mock_settings.email_from = 'test@example.com'
        
        success, error = send_email('to@example.com', 'Subject', 'Body')
        
        assert success is False
        assert 'Invalid SMTP URL' in error


class TestDeliverReminder:
    """Test reminder delivery with tracking."""
    
    @patch('app.services.reminders.send_reminder')
    def test_deliver_reminder_success(self, mock_send, db_session, test_user):
        mock_send.return_value = (True, None, 150)
        
        reminder = Reminder(
            user_id=test_user.id,
            message='Test reminder',
            send_at=datetime.utcnow(),
            channel='email',
        )
        db_session.add(reminder)
        db_session.commit()
        
        success = deliver_reminder(reminder)
        
        assert success is True
        assert reminder.sent is True
        assert reminder.delivered is True
        assert reminder.delivery_attempts == 1
        assert reminder.error_message is None
        
        # Check delivery record was created
        delivery = db_session.query(ReminderDelivery).filter_by(reminder_id=reminder.id).first()
        assert delivery is not None
        assert delivery.success is True
        assert delivery.response_time_ms == 150
    
    @patch('app.services.reminders.send_reminder')
    def test_deliver_reminder_failure_with_retry(self, mock_send, db_session, test_user):
        mock_send.return_value = (False, 'Connection timeout', 0)
        
        reminder = Reminder(
            user_id=test_user.id,
            message='Test reminder',
            send_at=datetime.utcnow(),
            channel='email',
        )
        db_session.add(reminder)
        db_session.commit()
        
        success = deliver_reminder(reminder)
        
        assert success is False
        assert reminder.delivered is False
        assert reminder.delivery_attempts == 1
        assert reminder.error_message == 'Connection timeout'
        assert reminder.sent is False  # Not marked as sent yet, will retry
        
        # Check that retry was scheduled
        assert reminder.send_at > datetime.utcnow()
    
    @patch('app.services.reminders.send_reminder')
    def test_deliver_reminder_max_retries_reached(self, mock_send, db_session, test_user):
        mock_send.return_value = (False, 'Permanent failure', 0)
        
        reminder = Reminder(
            user_id=test_user.id,
            message='Test reminder',
            send_at=datetime.utcnow(),
            channel='email',
            delivery_attempts=MAX_RETRY_ATTEMPTS - 1,  # One attempt away from max
        )
        db_session.add(reminder)
        db_session.commit()
        
        success = deliver_reminder(reminder)
        
        assert success is False
        assert reminder.sent is True  # Marked as processed even though failed
        assert reminder.delivered is False
        assert reminder.delivery_attempts == MAX_RETRY_ATTEMPTS


class TestDeliveryMetrics:
    """Test delivery metrics calculation."""
    
    def test_get_delivery_metrics_empty(self, db_session, test_user):
        metrics = get_delivery_metrics(test_user.id, days=30)
        
        assert metrics['total_attempts'] == 0
        assert metrics['success_rate'] == 0.0
    
    def test_get_delivery_metrics_with_data(self, db_session, test_user):
        # Create reminder with deliveries
        reminder = Reminder(
            user_id=test_user.id,
            message='Test',
            send_at=datetime.utcnow(),
            channel='email',
        )
        db_session.add(reminder)
        db_session.commit()
        
        # Create successful deliveries
        for i in range(3):
            delivery = ReminderDelivery(
                reminder_id=reminder.id,
                success=True,
                channel='email',
                response_time_ms=100 + i * 10,
            )
            db_session.add(delivery)
        
        # Create failed delivery
        delivery = ReminderDelivery(
            reminder_id=reminder.id,
            success=False,
            channel='email',
            error_message='Failed',
            response_time_ms=50,
        )
        db_session.add(delivery)
        db_session.commit()
        
        metrics = get_delivery_metrics(test_user.id, days=30)
        
        assert metrics['total_attempts'] == 4
        assert metrics['successful_deliveries'] == 3
        assert metrics['failed_deliveries'] == 1
        assert metrics['success_rate'] == 75.0
        assert metrics['average_response_time_ms'] == 95.0  # (100+110+120+50)/4
    
    def test_get_delivery_metrics_by_channel(self, db_session, test_user):
        reminder = Reminder(
            user_id=test_user.id,
            message='Test',
            send_at=datetime.utcnow(),
            channel='email',
        )
        db_session.add(reminder)
        db_session.commit()
        
        # Email deliveries - 2 success, 1 fail
        for _ in range(2):
            db_session.add(ReminderDelivery(reminder_id=reminder.id, success=True, channel='email'))
        db_session.add(ReminderDelivery(reminder_id=reminder.id, success=False, channel='email'))
        
        # WhatsApp deliveries - 1 success, 1 fail
        db_session.add(ReminderDelivery(reminder_id=reminder.id, success=True, channel='whatsapp:+123'))
        db_session.add(ReminderDelivery(reminder_id=reminder.id, success=False, channel='whatsapp:+123'))
        db_session.commit()
        
        metrics = get_delivery_metrics(test_user.id)
        
        assert metrics['by_channel']['email']['attempts'] == 3
        assert metrics['by_channel']['email']['success_rate'] == 66.67
        assert metrics['by_channel']['whatsapp']['attempts'] == 2
        assert metrics['by_channel']['whatsapp']['success_rate'] == 50.0


class TestFailedReminders:
    """Test retrieval of failed reminders."""
    
    def test_get_failed_reminders(self, db_session, test_user):
        # Create failed reminder (max retries reached)
        failed = Reminder(
            user_id=test_user.id,
            message='Failed reminder',
            send_at=datetime.utcnow(),
            channel='email',
            sent=True,
            delivered=False,
            delivery_attempts=MAX_RETRY_ATTEMPTS,
            last_attempt_at=datetime.utcnow(),
        )
        db_session.add(failed)
        
        # Create pending reminder (not failed yet)
        pending = Reminder(
            user_id=test_user.id,
            message='Pending',
            send_at=datetime.utcnow(),
            channel='email',
            sent=False,
            delivered=None,
            delivery_attempts=1,
        )
        db_session.add(pending)
        
        # Create successful reminder
        success = Reminder(
            user_id=test_user.id,
            message='Success',
            send_at=datetime.utcnow(),
            channel='email',
            sent=True,
            delivered=True,
            delivery_attempts=1,
        )
        db_session.add(success)
        db_session.commit()
        
        failed_reminders = get_failed_reminders(test_user.id)
        
        assert len(failed_reminders) == 1
        assert failed_reminders[0].id == failed.id
        assert failed_reminders[0].message == 'Failed reminder'


class TestRetryReminder:
    """Test manual retry functionality."""
    
    @patch('app.services.reminders.send_reminder')
    def test_retry_failed_reminder(self, mock_send, db_session, test_user, client, auth_headers):
        mock_send.return_value = (True, None, 100)
        
        reminder = Reminder(
            user_id=test_user.id,
            message='Failed reminder',
            send_at=datetime.utcnow(),
            channel='email',
            sent=True,
            delivered=False,
            delivery_attempts=MAX_RETRY_ATTEMPTS,
            error_message='Previous failure',
        )
        db_session.add(reminder)
        db_session.commit()
        
        response = client.post(
            f'/api/reminders/{reminder.id}/retry',
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['delivered'] is True
        assert data['attempts'] == 1  # Reset and then delivered
    
    def test_retry_already_delivered(self, db_session, test_user, client, auth_headers):
        reminder = Reminder(
            user_id=test_user.id,
            message='Already delivered',
            send_at=datetime.utcnow(),
            channel='email',
            sent=True,
            delivered=True,
            delivery_attempts=1,
        )
        db_session.add(reminder)
        db_session.commit()
        
        response = client.post(
            f'/api/reminders/{reminder.id}/retry',
            headers=auth_headers,
        )
        
        assert response.status_code == 400
        assert 'already delivered' in response.get_json()['error'].lower()
