# 🔔 Webhook Event System Implementation Guide

## Overview

This guide provides a comprehensive implementation plan for adding signed webhook event delivery to FinMind, enabling integrations and automation for key financial events.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   FinMind App   │────▶│  Webhook Service │────▶│  External URLs  │
│  (Event Source) │     │  (Queue+Retry)   │     │  (Subscribers)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Delivery Logs   │
                       │  (Audit Trail)   │
                       └──────────────────┘
```

---

## Event Types

### Core Events to Support

```python
class WebhookEventType(str, Enum):
    # User Events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    
    # Transaction Events
    TRANSACTION_CREATED = "transaction.created"
    TRANSACTION_UPDATED = "transaction.updated"
    TRANSACTION_DELETED = "transaction.deleted"
    
    # Budget Events
    BUDGET_CREATED = "budget.created"
    BUDGET_UPDATED = "budget.updated"
    BUDGET_EXCEEDED = "budget.exceeded"
    
    # Bill Events
    BILL_CREATED = "bill.created"
    BILL_UPDATED = "bill.updated"
    BILL_DUE_SOON = "bill.due_soon"
    BILL_PAID = "bill.paid"
    BILL_OVERDUE = "bill.overdue"
    
    # Category Events
    CATEGORY_CREATED = "category.created"
    CATEGORY_UPDATED = "category.updated"
    
    # Insight Events
    INSIGHT_GENERATED = "insight.generated"
    INSIGHT_ALERT = "insight.alert"
```

---

## Implementation

### Step 1: Database Models

**File:** `packages/backend/app/models/webhook.py`

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    events = Column(JSON, nullable=False)  # List of event types
    secret = Column(String(64), nullable=False)  # HMAC secret for signing
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="webhook_subscriptions")
    deliveries = relationship("WebhookDelivery", back_populates="subscription")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(String(36), ForeignKey("webhook_subscriptions.id"), nullable=False)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(32), default="pending")  # pending, success, failed
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    response_status = Column(Integer)
    response_body = Column(Text)
    error_message = Column(Text)
    next_retry_at = Column(DateTime)
    delivered_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    subscription = relationship("WebhookSubscription", back_populates="deliveries")
```

### Step 2: Webhook Service

**File:** `packages/backend/app/services/webhook_service.py`

```python
import hmac
import hashlib
import json
import httpx
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.webhook import WebhookSubscription, WebhookDelivery
from app.config import settings

class WebhookService:
    def __init__(self, db: Session):
        self.db = db
    
    def generate_signature(self, payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for webhook payload"""
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def verify_signature(self, payload: str, signature: str, secret: str) -> bool:
        """Verify webhook signature (for testing)"""
        expected = self.generate_signature(payload, secret)
        return hmac.compare_digest(expected, signature)
    
    def create_subscription(
        self,
        user_id: str,
        url: str,
        events: List[str],
        secret: Optional[str] = None
    ) -> WebhookSubscription:
        """Create a new webhook subscription"""
        import secrets
        
        subscription = WebhookSubscription(
            user_id=user_id,
            url=url,
            events=events,
            secret=secret or secrets.token_hex(32)
        )
        
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        
        return subscription
    
    def trigger_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Trigger webhook event for all matching subscriptions"""
        # Find active subscriptions for this event type
        subscriptions = self.db.query(WebhookSubscription).filter(
            WebhookSubscription.active == True,
            WebhookSubscription.events.contains([event_type])
        ).all()
        
        for subscription in subscriptions:
            self.queue_delivery(subscription, event_type, payload)
    
    def queue_delivery(
        self,
        subscription: WebhookSubscription,
        event_type: str,
        payload: Dict[str, Any]
    ) -> WebhookDelivery:
        """Queue webhook delivery for async processing"""
        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            event_type=event_type,
            payload=payload,
            status="pending",
            next_retry_at=datetime.utcnow()
        )
        
        self.db.add(delivery)
        self.db.commit()
        
        # Trigger async delivery (via Celery/RQ/Background task)
        from app.tasks.webhooks import deliver_webhook
        deliver_webhook.delay(delivery.id)
        
        return delivery
    
    def get_deliveries(
        self,
        subscription_id: str,
        limit: int = 50
    ) -> List[WebhookDelivery]:
        """Get delivery history for a subscription"""
        return self.db.query(WebhookDelivery).filter(
            WebhookDelivery.subscription_id == subscription_id
        ).order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
```

### Step 3: Async Delivery Task

**File:** `packages/backend/app/tasks/webhooks.py`

```python
from celery import Celery
from datetime import datetime, timedelta
import httpx
from app.services.webhook_service import WebhookService
from app.database import get_db

celery_app = Celery('webhooks', broker=settings.CELERY_BROKER_URL)

@celery_app.task(bind=True, max_retries=5)
def deliver_webhook(self, delivery_id: str) -> None:
    """Deliver webhook payload with retry logic"""
    db = next(get_db())
    
    try:
        delivery = db.query(WebhookDelivery).get(delivery_id)
        if not delivery:
            return
        
        subscription = delivery.subscription
        if not subscription or not subscription.active:
            delivery.status = "cancelled"
            db.commit()
            return
        
        # Prepare payload
        payload_json = json.dumps(delivery.payload, separators=(',', ':'))
        signature = WebhookService(db).generate_signature(
            payload_json,
            subscription.secret
        )
        
        # Send webhook
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": delivery.event_type,
            "X-Webhook-ID": delivery.id,
            "User-Agent": "FinMind-Webhooks/1.0"
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                subscription.url,
                content=payload_json,
                headers=headers
            )
            
            delivery.response_status = response.status_code
            delivery.response_body = response.text[:10000]  # Limit storage
            
            if response.status_code >= 200 and response.status_code < 300:
                delivery.status = "success"
                delivery.delivered_at = datetime.utcnow()
            else:
                raise Exception(f"HTTP {response.status_code}")
    
    except Exception as exc:
        delivery.attempts += 1
        delivery.error_message = str(exc)
        
        if delivery.attempts >= delivery.max_attempts:
            delivery.status = "failed"
        else:
            # Exponential backoff: 1min, 5min, 25min, 2h, 10h
            delay_minutes = 5 ** (delivery.attempts - 1)
            delivery.next_retry_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
            self.retry(countdown=delay_minutes * 60)
    
    finally:
        db.commit()
        db.close()
```

### Step 4: API Endpoints

**File:** `packages/backend/app/api/webhooks.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.services.webhook_service import WebhookService
from app.models.webhook import WebhookSubscription, WebhookDelivery
from pydantic import BaseModel, HttpUrl
from app.auth import get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

class CreateWebhookRequest(BaseModel):
    url: HttpUrl
    events: List[str]

class WebhookResponse(BaseModel):
    id: str
    url: str
    events: List[str]
    secret: str
    active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.post("", response_model=WebhookResponse)
def create_webhook(
    request: CreateWebhookRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new webhook subscription"""
    service = WebhookService(db)
    subscription = service.create_subscription(
        user_id=current_user.id,
        url=str(request.url),
        events=request.events
    )
    
    return subscription

@router.get("", response_model=List[WebhookResponse])
def list_webhooks(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all webhook subscriptions for current user"""
    return db.query(WebhookSubscription).filter(
        WebhookSubscription.user_id == current_user.id
    ).all()

@router.delete("/{webhook_id}")
def delete_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a webhook subscription"""
    subscription = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    db.delete(subscription)
    db.commit()
    
    return {"message": "Webhook deleted"}

@router.get("/{webhook_id}/deliveries")
def get_webhook_deliveries(
    webhook_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get delivery history for a webhook"""
    subscription = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    service = WebhookService(db)
    deliveries = service.get_deliveries(webhook_id, limit)
    
    return {
        "webhook_id": webhook_id,
        "deliveries": deliveries,
        "total": len(deliveries)
    }
```

### Step 5: Event Integration

**Example:** Trigger webhook when transaction is created

**File:** `packages/backend/app/api/transactions.py`

```python
from app.services.webhook_service import WebhookService

@router.post("/transactions", response_model=TransactionResponse)
def create_transaction(
    request: CreateTransactionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # ... existing transaction creation logic ...
    
    transaction = create_transaction_in_db(request, current_user)
    
    # Trigger webhook event
    webhook_service = WebhookService(db)
    webhook_service.trigger_event("transaction.created", {
        "id": transaction.id,
        "user_id": transaction.user_id,
        "amount": float(transaction.amount),
        "category": transaction.category.name if transaction.category else None,
        "description": transaction.description,
        "date": transaction.date.isoformat(),
        "created_at": transaction.created_at.isoformat()
    })
    
    return transaction
```

### Step 6: Documentation

**File:** `docs/webhooks.md`

```markdown
# Webhook Events

FinMind sends webhook events to notify your application about important actions.

## Event Types

### Transaction Events

#### `transaction.created`
Triggered when a new transaction is created.

**Payload:**
```json
{
  "id": "txn_123",
  "user_id": "usr_456",
  "amount": 50.00,
  "category": "Food",
  "description": "Lunch",
  "date": "2026-03-24",
  "created_at": "2026-03-24T12:00:00Z"
}
```

### Bill Events

#### `bill.due_soon`
Triggered 3 days before a bill is due.

**Payload:**
```json
{
  "id": "bill_789",
  "name": "Electric Bill",
  "amount": 120.00,
  "due_date": "2026-03-27",
  "paid": false
}
```

## Security

All webhooks are signed using HMAC-SHA256. Verify signatures using the `X-Webhook-Signature` header.

**Example (Node.js):**
```javascript
const crypto = require('crypto');

function verifySignature(payload, signature, secret) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  
  return `sha256=${expected}` === signature;
}
```

## Retry Policy

Failed deliveries are retried with exponential backoff:
- Attempt 1: Immediate
- Attempt 2: 1 minute
- Attempt 3: 5 minutes
- Attempt 4: 25 minutes
- Attempt 5: 2 hours

After 5 failed attempts, the delivery is marked as failed.

## Testing

Use [webhook.site](https://webhook.site) to test your webhook integration.
```

---

## Testing

### Unit Tests

**File:** `packages/backend/tests/test_webhooks.py`

```python
import pytest
from app.services.webhook_service import WebhookService

def test_generate_signature():
    service = WebhookService(db)
    payload = '{"event": "test"}'
    secret = "test_secret"
    
    signature = service.generate_signature(payload, secret)
    assert signature.startswith("sha256=")
    assert len(signature) == 71  # sha256= + 64 hex chars

def test_verify_signature():
    service = WebhookService(db)
    payload = '{"event": "test"}'
    secret = "test_secret"
    
    signature = service.generate_signature(payload, secret)
    assert service.verify_signature(payload, signature, secret) == True
    assert service.verify_signature(payload, "invalid", secret) == False
```

### Integration Tests

```python
def test_webhook_delivery():
    # Create test webhook subscription
    # Trigger event
    # Verify delivery was attempted
    # Verify signature in request
    pass
```

---

## Acceptance Criteria Checklist

- [x] Signed delivery (HMAC-SHA256)
- [x] Retry & failure handling (5 attempts, exponential backoff)
- [x] Event types documented (15+ event types)
- [ ] Database models created
- [ ] Service implementation
- [ ] Async delivery task
- [ ] API endpoints
- [ ] Event integration examples
- [ ] Unit tests
- [ ] Integration tests

---

## Files to Create/Modify

### New Files
- `packages/backend/app/models/webhook.py`
- `packages/backend/app/services/webhook_service.py`
- `packages/backend/app/tasks/webhooks.py`
- `packages/backend/app/api/webhooks.py`
- `packages/backend/tests/test_webhooks.py`
- `docs/webhooks.md`

### Modified Files
- `packages/backend/app/api/transactions.py` (add webhook triggers)
- `packages/backend/app/api/bills.py` (add webhook triggers)
- `packages/backend/app/api/users.py` (add webhook triggers)
- `packages/backend/app/models/__init__.py` (register new models)
- `packages/backend/app/config.py` (add webhook settings)

---

**Time Estimate:** 6-8 hours
**Difficulty:** Medium-Hard
**Bounty Value:** $50
