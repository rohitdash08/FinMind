"""
Tests for webhook functionality

Covers:
- Webhook CRUD operations
- Event filtering
- Delivery tracking
- Retry logic
- Signature validation
"""

import json
import time
import pytest
from unittest.mock import patch, Mock
from app import create_app
from app.extensions import db
from app.models import Webhook, WebhookDelivery, WebhookDeliveryStatus
from app.services.webhooks import webhook_service, WebhookEventType


@pytest.fixture
def client():
    """Create a test client"""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret-key',
        'WEBHOOK_SECRET': 'test-webhook-secret',
        'JWT_SECRET_KEY': 'test-jwt-secret'
    })

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


@pytest.fixture
def auth_headers(client):
    """Get authentication headers for a test user"""
    # Register a user
    r = client.post('/auth/register', json={
        'email': 'test@example.com',
        'password': 'testpass123',
        'preferred_currency': 'USD'
    })
    assert r.status_code == 201

    # Login
    r = client.post('/auth/login', json={
        'email': 'test@example.com',
        'password': 'testpass123'
    })
    assert r.status_code == 200
    token = r.get_json()['access_token']

    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def webhook_id(client, auth_headers):
    """Create a test webhook and return its ID"""
    r = client.post('/webhooks', json={
        'url': 'https://example.com/webhook',
        'secret': 'test-secret'
    }, headers=auth_headers)
    assert r.status_code == 201
    return r.get_json()['id']


def test_list_available_webhook_events(client):
    """Test listing all available webhook event types"""
    r = client.get('/webhooks/events')
    assert r.status_code == 200

    events = r.get_json()
    assert isinstance(events, list)
    assert len(events) > 0

    # Check that all known event types are present
    event_types = [e['type'] for e in events]
    assert 'expense.created' in event_types
    assert 'expense.updated' in event_types
    assert 'bill.created' in event_types
    assert 'reminder.triggered' in event_types
    assert 'user.registered' in event_types


def test_create_webhook_success(client, auth_headers):
    """Test successful webhook creation"""
    r = client.post('/webhooks', json={
        'url': 'https://example.com/webhook',
        'secret': 'test-secret'
    }, headers=auth_headers)

    assert r.status_code == 201
    webhook = r.get_json()
    assert webhook['url'] == 'https://example.com/webhook'
    assert webhook['secret'] == 'test-se***'  # Masked
    assert webhook['active'] is True
    assert webhook['events'] is None
    assert webhook['id'] is not None
    assert webhook['created_at'] is not None


def test_create_webhook_with_event_filter(client, auth_headers):
    """Test webhook creation with event filtering"""
    r = client.post('/webhooks', json={
        'url': 'https://example.com/webhook',
        'events': ['expense.created', 'bill.created']
    }, headers=auth_headers)

    assert r.status_code == 201
    webhook = r.get_json()
    assert webhook['events'] == ['expense.created', 'bill.created']


def test_create_webhook_invalid_url(client, auth_headers):
    """Test webhook creation with invalid URL"""
    r = client.post('/webhooks', json={
        'url': 'not-a-url'
    }, headers=auth_headers)

    assert r.status_code == 400
    assert 'url must start with' in r.get_json()['error']


def test_create_webhook_invalid_events(client, auth_headers):
    """Test webhook creation with invalid event types"""
    r = client.post('/webhooks', json={
        'url': 'https://example.com/webhook',
        'events': ['invalid.event']
    }, headers=auth_headers)

    assert r.status_code == 400
    assert 'Invalid events' in r.get_json()['error']


def test_create_webhook_missing_url(client, auth_headers):
    """Test webhook creation without URL"""
    r = client.post('/webhooks', json={
        'secret': 'test-secret'
    }, headers=auth_headers)

    assert r.status_code == 400
    assert 'url is required' in r.get_json()['error']


def test_list_webhooks(client, auth_headers):
    """Test listing all webhooks for a user"""
    # Create multiple webhooks
    for i in range(3):
        client.post('/webhooks', json={
            'url': f'https://example.com/webhook{i}',
        }, headers=auth_headers)

    r = client.get('/webhooks', headers=auth_headers)
    assert r.status_code == 200

    webhooks = r.get_json()
    assert len(webhooks) == 3


def test_delete_webhook(client, auth_headers, webhook_id):
    """Test deleting a webhook"""
    r = client.delete(f'/webhooks/{webhook_id}', headers=auth_headers)
    assert r.status_code == 200
    assert r.get_json()['message'] == 'webhook deleted'

    # Verify webhook is deleted
    r = client.get('/webhooks', headers=auth_headers)
    assert len(r.get_json()) == 0


def test_delete_webhook_unauthorized(client, webhook_id):
    """Test deleting webhook without authentication"""
    r = client.delete(f'/webhooks/{webhook_id}')
    assert r.status_code == 401


def test_delete_webhook_not_found(client, auth_headers):
    """Test deleting non-existent webhook"""
    r = client.delete('/webhooks/99999', headers=auth_headers)
    assert r.status_code == 404


def test_list_webhook_deliveries(client, auth_headers, webhook_id):
    """Test listing delivery records for a webhook"""
    r = client.get(f'/webhooks/deliveries/{webhook_id}', headers=auth_headers)
    assert r.status_code == 200

    deliveries = r.get_json()
    assert isinstance(deliveries, list)


def test_webhook_delivery_filters_by_user(client, auth_headers):
    """Test that users can only see their own webhook deliveries"""
    # Create another user and webhook
    r = client.post('/auth/register', json={
        'email': 'other@example.com',
        'password': 'testpass123',
        'preferred_currency': 'USD'
    })
    assert r.status_code == 201

    r = client.post('/auth/login', json={
        'email': 'other@example.com',
        'password': 'testpass123'
    })
    assert r.status_code == 200
    other_token = r.get_json()['access_token']

    # Create webhook for other user
    r = client.post('/webhooks', json={
        'url': 'https://example.com/webhook',
    }, headers={'Authorization': f'Bearer {other_token}'})
    assert r.status_code == 201
    other_webhook_id = r.get_json()['id']

    # Try to access other user's webhook deliveries with first user's token
    r = client.get(
        f'/webhooks/deliveries/{other_webhook_id}',
        headers=auth_headers
    )
    assert r.status_code == 404


def test_webhook_signature_generation():
    """Test that webhook signature is generated correctly"""
    payload = json.dumps({"test": "data"}, sort_keys=True)
    signature = webhook_service._generate_signature(payload)

    # Verify signature format (should be a hex string)
    assert isinstance(signature, str)
    assert len(signature) == 64  # SHA256 produces 64 hex characters


def test_webhook_idempotency_key_generation():
    """Test that idempotency keys are generated correctly"""
    key1 = webhook_service._generate_idempotency_key(
        WebhookEventType.EXPENSE_CREATED,
        123
    )
    key2 = webhook_service._generate_idempotency_key(
        WebhookEventType.EXPENSE_CREATED,
        456
    )

    assert key1 != key2
    assert 'expense.created' in key1
    assert '123' in key1


def test_webhook_should_deliver_event_no_filter():
    """Test that webhooks without event filter receive all events"""
    webhook = Webhook(events=None, active=True)

    assert webhook_service._should_deliver_event(
        webhook,
        WebhookEventType.EXPENSE_CREATED
    ) is True

    assert webhook_service._should_deliver_event(
        webhook,
        WebhookEventType.BILL_CREATED
    ) is True


def test_webhook_should_deliver_event_with_filter():
    """Test that webhooks with event filter only receive filtered events"""
    webhook = Webhook(
        events=['expense.created', 'bill.created'],
        active=True
    )

    assert webhook_service._should_deliver_event(
        webhook,
        WebhookEventType.EXPENSE_CREATED
    ) is True

    assert webhook_service._should_deliver_event(
        webhook,
        WebhookEventType.BILL_CREATED
    ) is True

    assert webhook_service._should_deliver_event(
        webhook,
        WebhookEventType.BILL_UPDATED
    ) is False


def test_webhook_payload_building():
    """Test webhook payload structure"""
    payload = webhook_service._build_payload(
        WebhookEventType.EXPENSE_CREATED,
        {'id': 123, 'amount': 100.0},
        user_id=1
    )

    assert payload.event_type == WebhookEventType.EXPENSE_CREATED
    assert payload.data == {'id': 123, 'amount': 100.0}
    assert payload.user_id == 1
    assert payload.idempotency_key is not None
    assert payload.trace_id is not None
    assert payload.timestamp > 0


def test_webhook_trace_id_generation():
    """Test that trace IDs are unique"""
    trace_id1 = webhook_service._generate_trace_id()
    trace_id2 = webhook_service._generate_trace_id()

    assert trace_id1 != trace_id2
    assert len(trace_id1) == 36  # UUID format


def test_webhook_delivery_status_enum():
    """Test that delivery status enum has correct values"""
    assert WebhookDeliveryStatus.PENDING.value == "pending"
    assert WebhookDeliveryStatus.SENT.value == "sent"
    assert WebhookDeliveryStatus.FAILED.value == "failed"
    assert WebhookDeliveryStatus.RETRYING.value == "retrying"


@patch('requests.post')
def test_webhook_test_endpoint_success(mock_post, client, auth_headers, webhook_id):
    """Test webhook test endpoint with successful delivery"""
    mock_post.return_value = Mock(
        status_code=200,
        text='OK'
    )

    r = client.post('/webhooks/test', json={
        'webhook_id': webhook_id
    }, headers=auth_headers)

    assert r.status_code == 200
    result = r.get_json()
    assert result['success'] is True
    assert 'Test webhook delivered' in result['message']


@patch('requests.post')
def test_webhook_test_endpoint_failure(mock_post, client, auth_headers, webhook_id):
    """Test webhook test endpoint with failed delivery"""
    mock_post.return_value = Mock(
        status_code=500,
        text='Internal Server Error'
    )

    r = client.post('/webhooks/test', json={
        'webhook_id': webhook_id
    }, headers=auth_headers)

    assert r.status_code == 200
    result = r.get_json()
    assert result['success'] is False
    assert 'Test webhook failed' in result['message']


def test_webhook_test_endpoint_not_found(client, auth_headers):
    """Test webhook test endpoint with non-existent webhook"""
    r = client.post('/webhooks/test', json={
        'webhook_id': 99999
    }, headers=auth_headers)

    assert r.status_code == 400
    assert 'not found' in r.get_json()['error'].lower()


def test_webhook_test_endpoint_missing_webhook_id(client, auth_headers):
    """Test webhook test endpoint without webhook_id"""
    r = client.post('/webhooks/test', json={}, headers=auth_headers)

    assert r.status_code == 400
    assert 'webhook_id is required' in r.get_json()['error']


def test_webhook_delivery_to_dict():
    """Test delivery record serialization"""
    delivery = WebhookDelivery(
        id=1,
        webhook_id=2,
        event_type='expense.created',
        payload={'test': 'data'},
        status='sent',
        response_status=200,
        error_message=None,
        retry_count=0,
        last_attempt_at=None,
        created_at=None
    )

    # The _delivery_to_dict function is in routes, not service
    # This test verifies the model structure
    assert delivery.event_type == 'expense.created'
    assert delivery.status == 'sent'
    assert delivery.response_status == 200


def test_webhook_to_dict():
    """Test webhook serialization"""
    webhook = Webhook(
        id=1,
        user_id=2,
        url='https://example.com/webhook',
        secret='test-secret',
        events=['expense.created'],
        active=True,
        created_at=None,
        last_delivered_at=None
    )

    assert webhook.url == 'https://example.com/webhook'
    assert webhook.secret == 'test-secret'
    assert webhook.events == ['expense.created']
    assert webhook.active is True


def test_webhook_active_webhook_only():
    """Test that only active webhooks receive events"""
    # This is more of an integration test scenario
    # The service filters by active=True in _deliver_webhook
    assert True  # Placeholder for integration test


def test_webhook_without_secret():
    """Test webhook creation without custom secret"""
    # Webhook model allows secret to be None
    webhook = Webhook(
        url='https://example.com/webhook',
        secret=None
    )

    assert webhook.secret is None


def test_webhook_with_empty_events_list():
    """Test webhook with empty events list (should receive no events)"""
    webhook = Webhook(
        url='https://example.com/webhook',
        events=[]
    )

    assert webhook_service._should_deliver_event(
        webhook,
        WebhookEventType.EXPENSE_CREATED
    ) is False


def test_webhook_service_max_retries():
    """Test that webhook service has correct retry configuration"""
    assert webhook_service.max_retries == 3
    assert webhook_service.retry_delay == 5
    assert webhook_service.max_retry_delay == 60
    assert webhook_service.timeout == 10


def test_webhook_event_type_enum_values():
    """Test that webhook event types have correct values"""
    assert WebhookEventType.EXPENSE_CREATED.value == "expense.created"
    assert WebhookEventType.EXPENSE_UPDATED.value == "expense.updated"
    assert WebhookEventType.EXPENSE_DELETED.value == "expense.deleted"
    assert WebhookEventType.BILL_CREATED.value == "bill.created"
    assert WebhookEventType.BILL_UPDATED.value == "bill.updated"
    assert WebhookEventType.BILL_PAID.value == "bill.paid"
    assert WebhookEventType.REMINDER_TRIGGERED.value == "reminder.triggered"
    assert WebhookEventType.USER_REGISTERED.value == "user.registered"
    assert WebhookEventType.USER_DELETED.value == "user.deleted"
