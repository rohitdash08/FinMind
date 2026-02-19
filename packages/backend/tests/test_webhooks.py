"""
Tests for webhook system.
"""
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.models import Webhook, WebhookEvent, User, db
from app.services.webhooks import (
    generate_webhook_secret,
    sign_webhook_payload,
    verify_webhook_signature,
    create_webhook,
    get_user_webhooks,
    delete_webhook,
    update_webhook,
    emit_event,
    deliver_webhook_events,
    get_webhook_event_docs
)


@pytest.fixture
def test_user(app):
    """Create a test user."""
    user = User(email="test@example.com", password_hash="hash", role="USER")
    db.session.add(user)
    db.session.commit()
    return user


class TestWebhookSignature:
    """Test webhook signing and verification."""
    
    def test_generate_secret(self):
        """Test secret generation."""
        secret = generate_webhook_secret()
        assert secret
        assert len(secret) > 20
    
    def test_sign_payload(self):
        """Test payload signing."""
        payload = '{"test": "data"}'
        secret = "test-secret"
        signature = sign_webhook_payload(payload, secret)
        
        assert signature
        assert len(signature) == 64  # SHA256 hex is 64 chars
    
    def test_verify_valid_signature(self):
        """Test signature verification with valid signature."""
        payload = '{"test": "data"}'
        secret = "test-secret"
        signature = sign_webhook_payload(payload, secret)
        
        assert verify_webhook_signature(signature, payload, secret)
    
    def test_verify_invalid_signature(self):
        """Test signature verification with invalid signature."""
        payload = '{"test": "data"}'
        secret = "test-secret"
        
        assert not verify_webhook_signature("invalid", payload, secret)
    
    def test_verify_wrong_secret(self):
        """Test signature verification with wrong secret."""
        payload = '{"test": "data"}'
        secret = "test-secret"
        signature = sign_webhook_payload(payload, secret)
        
        assert not verify_webhook_signature(signature, payload, "wrong-secret")


class TestWebhookCRUD:
    """Test webhook CRUD operations."""
    
    def test_create_webhook(self, test_user):
        """Test creating a webhook."""
        webhook = create_webhook(
            test_user.id,
            "https://example.com/webhook",
            ["expense.created", "bill.paid"]
        )
        
        assert webhook.id
        assert webhook.user_id == test_user.id
        assert webhook.url == "https://example.com/webhook"
        assert webhook.active
        assert webhook.secret
        assert json.loads(webhook.events) == ["expense.created", "bill.paid"]
    
    def test_get_user_webhooks(self, test_user):
        """Test getting user's webhooks."""
        create_webhook(test_user.id, "https://example.com/1", ["expense.created"])
        create_webhook(test_user.id, "https://example.com/2", ["bill.paid"])
        
        webhooks = get_user_webhooks(test_user.id)
        assert len(webhooks) == 2
    
    def test_get_active_webhooks_only(self, test_user):
        """Test getting only active webhooks."""
        w1 = create_webhook(test_user.id, "https://example.com/1", ["expense.created"])
        w2 = create_webhook(test_user.id, "https://example.com/2", ["bill.paid"])
        
        # Deactivate one
        w2.active = False
        db.session.commit()
        
        webhooks = get_user_webhooks(test_user.id, active_only=True)
        assert len(webhooks) == 1
        assert webhooks[0].id == w1.id
    
    def test_update_webhook(self, test_user):
        """Test updating a webhook."""
        webhook = create_webhook(test_user.id, "https://example.com/1", ["expense.created"])
        
        updated = update_webhook(
            webhook.id,
            test_user.id,
            url="https://example.com/updated",
            events=["bill.paid"]
        )
        
        assert updated.url == "https://example.com/updated"
        assert json.loads(updated.events) == ["bill.paid"]
    
    def test_delete_webhook(self, test_user):
        """Test deleting a webhook."""
        webhook = create_webhook(test_user.id, "https://example.com/1", ["expense.created"])
        
        assert delete_webhook(webhook.id, test_user.id)
        
        # Verify it's deactivated
        webhook = Webhook.query.get(webhook.id)
        assert not webhook.active
    
    def test_delete_nonexistent_webhook(self, test_user):
        """Test deleting a webhook that doesn't exist."""
        assert not delete_webhook(99999, test_user.id)
    
    def test_update_nonexistent_webhook(self, test_user):
        """Test updating a webhook that doesn't exist."""
        result = update_webhook(99999, test_user.id, url="https://example.com")
        assert result is None


class TestWebhookEvents:
    """Test webhook event emission and delivery."""
    
    @patch('app.services.webhooks.redis_client')
    def test_emit_event(self, mock_redis, test_user):
        """Test emitting a webhook event."""
        webhook = create_webhook(
            test_user.id,
            "https://example.com/webhook",
            ["expense.created"]
        )
        
        emit_event(test_user.id, "expense.created", {"id": 123, "amount": 50})
        
        # Check that event was created
        event = WebhookEvent.query.filter_by(webhook_id=webhook.id).first()
        assert event
        assert event.event_type == "expense.created"
        assert event.status == "pending"
        
        # Check that it was queued
        mock_redis.lpush.assert_called_once()
    
    def test_emit_event_not_subscribed(self, test_user):
        """Test emitting an event that webhook isn't subscribed to."""
        webhook = create_webhook(
            test_user.id,
            "https://example.com/webhook",
            ["bill.paid"]  # Only subscribed to bill.paid
        )
        
        emit_event(test_user.id, "expense.created", {"id": 123})
        
        # Check that event was NOT created
        events = WebhookEvent.query.filter_by(webhook_id=webhook.id).all()
        assert len(events) == 0
    
    @patch('requests.post')
    def test_deliver_webhook_success(self, mock_post, test_user):
        """Test successful webhook delivery."""
        webhook = create_webhook(
            test_user.id,
            "https://example.com/webhook",
            ["expense.created"]
        )
        
        # Create an event manually
        payload = json.dumps({"type": "expense.created", "data": {"id": 123}})
        event = WebhookEvent(
            webhook_id=webhook.id,
            event_type="expense.created",
            payload=payload,
            status="pending"
        )
        db.session.add(event)
        db.session.commit()
        
        # Mock successful response
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()
        
        stats = deliver_webhook_events(batch_size=10)
        
        assert stats['processed'] == 1
        assert stats['delivered'] == 1
        assert stats['failed'] == 0
        
        # Check event status
        event = WebhookEvent.query.get(event.id)
        assert event.status == "delivered"
        assert event.delivered_at is not None
        assert event.delivery_attempts == 1
        
        # Check that request was made with correct headers
        call_args = mock_post.call_args
        assert call_args[1]['url'] == "https://example.com/webhook"
        assert 'X-FinMind-Signature' in call_args[1]['headers']
        assert 'X-FinMind-Timestamp' in call_args[1]['headers']
        assert 'X-FinMind-Event-Id' in call_args[1]['headers']
    
    @patch('requests.post')
    def test_deliver_webhook_retry(self, mock_post, test_user):
        """Test webhook delivery retry on failure."""
        webhook = create_webhook(
            test_user.id,
            "https://example.com/webhook",
            ["expense.created"]
        )
        
        payload = json.dumps({"type": "expense.created", "data": {"id": 123}})
        event = WebhookEvent(
            webhook_id=webhook.id,
            event_type="expense.created",
            payload=payload,
            status="pending"
        )
        db.session.add(event)
        db.session.commit()
        
        # Mock failed response
        mock_post.side_effect = Exception("Connection failed")
        
        stats = deliver_webhook_events(batch_size=10)
        
        assert stats['processed'] == 1
        assert stats['delivered'] == 0
        assert stats['failed'] == 1
        
        # Check event status - should still be pending for retry
        event = WebhookEvent.query.get(event.id)
        assert event.status == "pending"
        assert event.delivery_attempts == 1
        assert event.last_error
    
    @patch('requests.post')
    def test_deliver_webhook_max_retries(self, mock_post, test_user):
        """Test webhook delivery after max retries."""
        webhook = create_webhook(
            test_user.id,
            "https://example.com/webhook",
            ["expense.created"]
        )
        
        payload = json.dumps({"type": "expense.created", "data": {"id": 123}})
        event = WebhookEvent(
            webhook_id=webhook.id,
            event_type="expense.created",
            payload=payload,
            status="pending",
            delivery_attempts=4  # One away from max
        )
        db.session.add(event)
        db.session.commit()
        
        # Mock failed response
        mock_post.side_effect = Exception("Connection failed")
        
        stats = deliver_webhook_events(batch_size=10)
        
        # After 5th attempt, should be marked as failed
        event = WebhookEvent.query.get(event.id)
        assert event.status == "failed"
        assert event.delivery_attempts == 5


class TestWebhookDocs:
    """Test webhook documentation."""
    
    def test_get_event_docs(self):
        """Test getting webhook event documentation."""
        docs = get_webhook_event_docs()
        
        assert "expense.created" in docs
        assert "bill.paid" in docs
        assert "category.created" in docs
        assert docs["expense.created"]  # Should have description
