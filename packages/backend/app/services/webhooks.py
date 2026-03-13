import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
from sqlalchemy import or_

from ..observability import track_webhook_delivery_event
from ..extensions import db
from ..models import WebhookDelivery, WebhookEvent, WebhookTarget


class WebhookService:
    MAX_RETRIES = 7
    REQUEST_TIMEOUT_SECONDS = 10
    SUCCESS_STATUS_CODES = {200, 201, 202, 204}

    _EVENT_DESCRIPTIONS = {
        WebhookEvent.EXPENSE_CREATED.value: "Triggered when a new expense is created.",
        WebhookEvent.EXPENSE_UPDATED.value: "Triggered when an expense is updated.",
        WebhookEvent.EXPENSE_DELETED.value: "Triggered when an expense is deleted.",
        WebhookEvent.BILL_CREATED.value: "Triggered when a new bill is created.",
        WebhookEvent.BILL_UPDATED.value: "Triggered when a bill is updated.",
        WebhookEvent.BILL_DELETED.value: "Triggered when a bill is deleted.",
        WebhookEvent.BILL_DUE.value: "Triggered when a bill becomes due.",
        WebhookEvent.SUBSCRIPTION_UPDATED.value: (
            "Triggered when a subscription changes."
        ),
        WebhookEvent.PROFILE_UPDATED.value: "Triggered when a user profile changes.",
    }

    _EVENT_EXAMPLES = {
        WebhookEvent.EXPENSE_CREATED.value: {
            "id": 123,
            "amount": 42.5,
            "currency": "INR",
            "category_id": 3,
            "expense_type": "EXPENSE",
            "description": "Lunch",
            "date": "2026-03-01",
        },
        WebhookEvent.EXPENSE_UPDATED.value: {
            "id": 123,
            "amount": 45.0,
            "currency": "INR",
            "category_id": 3,
            "expense_type": "EXPENSE",
            "description": "Lunch (updated)",
            "date": "2026-03-01",
        },
        WebhookEvent.EXPENSE_DELETED.value: {
            "id": 123,
            "amount": 45.0,
            "currency": "INR",
            "category_id": 3,
            "expense_type": "EXPENSE",
            "description": "Lunch (updated)",
            "date": "2026-03-01",
        },
        WebhookEvent.BILL_CREATED.value: {
            "id": 101,
            "name": "Electricity",
            "amount": 1500.0,
            "currency": "INR",
            "next_due_date": "2026-03-28",
            "cadence": "MONTHLY",
            "autopay_enabled": False,
            "channel_whatsapp": False,
            "channel_email": True,
        },
        WebhookEvent.BILL_UPDATED.value: {
            "id": 101,
            "name": "Electricity",
            "amount": 1600.0,
            "currency": "INR",
            "next_due_date": "2026-04-28",
            "cadence": "MONTHLY",
            "autopay_enabled": True,
            "channel_whatsapp": False,
            "channel_email": True,
            "active": True,
        },
        WebhookEvent.BILL_DELETED.value: {"id": 101},
        WebhookEvent.BILL_DUE.value: {
            "id": 101,
            "name": "Electricity",
            "amount": 1600.0,
            "currency": "INR",
            "due_date": "2026-04-28",
        },
        WebhookEvent.SUBSCRIPTION_UPDATED.value: {
            "id": 5,
            "plan_id": 2,
            "active": True,
            "started_at": "2026-01-01T00:00:00Z",
        },
        WebhookEvent.PROFILE_UPDATED.value: {
            "id": 42,
            "email": "user@example.com",
            "preferred_currency": "INR",
        },
    }

    @staticmethod
    def generate_signature(secret: str, payload: str, timestamp: str) -> str:
        message = f"{timestamp}.{payload}"
        return hmac.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def event_types_catalog() -> list[dict]:
        types = []
        for event in WebhookEvent:
            types.append(
                {
                    "type": event.value,
                    "description": WebhookService._EVENT_DESCRIPTIONS[event.value],
                    "payload_example": WebhookService._EVENT_EXAMPLES[event.value],
                }
            )
        return types

    @staticmethod
    def create_target(
        *, user_id: int, url: str, secret: str, events: list[str] | None
    ) -> WebhookTarget:
        WebhookService._validate_url(url)
        if not secret:
            raise ValueError("secret is required")
        normalized_events = WebhookService._normalize_events(events)

        target = WebhookTarget(
            user_id=user_id,
            url=url,
            secret=secret,
            events=normalized_events,
            enabled=True,
        )
        db.session.add(target)
        db.session.commit()
        return target

    @staticmethod
    def get_targets(*, user_id: int) -> list[WebhookTarget]:
        return (
            WebhookTarget.query.filter_by(user_id=user_id)
            .order_by(WebhookTarget.created_at.desc())
            .all()
        )

    @staticmethod
    def update_target(
        *,
        target_id: int,
        user_id: int,
        url: str | None = None,
        secret: str | None = None,
        events: list[str] | None = None,
        enabled: bool | None = None,
    ) -> WebhookTarget | None:
        target = WebhookTarget.query.filter_by(id=target_id, user_id=user_id).first()
        if not target:
            return None

        if url is not None:
            WebhookService._validate_url(url)
            target.url = url
        if secret is not None:
            if not secret:
                raise ValueError("secret cannot be empty")
            target.secret = secret
        if events is not None:
            target.events = WebhookService._normalize_events(events)
        if enabled is not None:
            target.enabled = bool(enabled)

        db.session.commit()
        return target

    @staticmethod
    def delete_target(*, target_id: int, user_id: int) -> bool:
        target = WebhookTarget.query.filter_by(id=target_id, user_id=user_id).first()
        if not target:
            return False
        db.session.delete(target)
        db.session.commit()
        return True

    @staticmethod
    def get_deliveries(
        *, user_id: int, target_id: int | None = None
    ) -> list[WebhookDelivery]:
        query = WebhookDelivery.query.join(
            WebhookTarget, WebhookTarget.id == WebhookDelivery.target_id
        ).filter(WebhookTarget.user_id == user_id)
        if target_id is not None:
            query = query.filter(WebhookDelivery.target_id == target_id)
        return query.order_by(WebhookDelivery.created_at.desc()).all()

    @staticmethod
    def get_delivery_summary(
        *, user_id: int, target_id: int | None = None
    ) -> dict[str, object]:
        now = datetime.utcnow()
        query = WebhookDelivery.query.join(
            WebhookTarget, WebhookTarget.id == WebhookDelivery.target_id
        ).filter(WebhookTarget.user_id == user_id)
        target_query = WebhookTarget.query.filter(WebhookTarget.user_id == user_id)
        if target_id is not None:
            query = query.filter(WebhookDelivery.target_id == target_id)
            target_query = target_query.filter(WebhookTarget.id == target_id)

        deliveries = query.order_by(WebhookDelivery.created_at.asc()).all()
        pending = [item for item in deliveries if item.status == "pending"]
        failed = [item for item in deliveries if item.status == "failed"]
        success = [item for item in deliveries if item.status == "success"]
        due_now = [
            item
            for item in pending
            if item.next_attempt_at is None or item.next_attempt_at <= now
        ]
        scheduled = [
            item
            for item in pending
            if item.next_attempt_at is not None and item.next_attempt_at > now
        ]
        oldest_pending = pending[0].created_at if pending else None
        latest_failure = max(
            (
                item.updated_at or item.last_attempt_at or item.created_at
                for item in failed
            ),
            default=None,
        )

        return {
            "targets_total": target_query.count(),
            "max_retries": WebhookService.MAX_RETRIES,
            "deliveries": {
                "pending": len(pending),
                "success": len(success),
                "failed": len(failed),
                "total": len(deliveries),
            },
            "retry_backlog": {
                "due_now": len(due_now),
                "scheduled": len(scheduled),
            },
            "oldest_pending": oldest_pending.isoformat() if oldest_pending else None,
            "latest_failure": latest_failure.isoformat() if latest_failure else None,
        }

    @staticmethod
    def trigger_event(
        event_type: WebhookEvent | str, payload: dict, user_id: int | None = None
    ) -> int:
        event_name = WebhookService._normalize_event_name(event_type)

        query = WebhookTarget.query.filter_by(enabled=True)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        targets = query.all()

        envelope = {
            "type": event_name,
            "timestamp": int(time.time()),
            "data": payload,
        }
        if user_id is not None:
            envelope["user_id"] = user_id

        created = 0
        for target in targets:
            if not WebhookService._target_subscribed(target, event_name):
                continue
            db.session.add(
                WebhookDelivery(
                    target_id=target.id,
                    event_type=event_name,
                    payload=envelope,
                    status="pending",
                    attempt_count=0,
                    next_attempt_at=datetime.utcnow(),
                )
            )
            created += 1

        if created == 0:
            return 0

        db.session.commit()
        WebhookService.process_pending_deliveries()
        return created

    @staticmethod
    def process_pending_deliveries(limit: int = 100) -> int:
        now = datetime.utcnow()
        pending = (
            WebhookDelivery.query.filter(WebhookDelivery.status == "pending")
            .filter(
                or_(
                    WebhookDelivery.next_attempt_at.is_(None),
                    WebhookDelivery.next_attempt_at <= now,
                )
            )
            .order_by(WebhookDelivery.created_at.asc())
            .limit(limit)
            .all()
        )
        for delivery in pending:
            WebhookService.attempt_delivery(delivery)
        return len(pending)

    @staticmethod
    def attempt_delivery(delivery: WebhookDelivery) -> None:
        target = db.session.get(WebhookTarget, delivery.target_id)
        now = datetime.utcnow()

        delivery.attempt_count += 1
        delivery.last_attempt_at = now

        if not target or not target.enabled:
            delivery.status = "failed"
            delivery.next_attempt_at = None
            delivery.response_body = "target not found or disabled"
            db.session.commit()
            track_webhook_delivery_event(delivery.event_type, "target_unavailable")
            return

        payload_json = json.dumps(
            delivery.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        timestamp = str(int(time.time()))
        signature = WebhookService.generate_signature(
            target.secret, payload_json, timestamp
        )

        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Event": delivery.event_type,
            "X-FinMind-Timestamp": timestamp,
            "X-FinMind-Signature": f"sha256={signature}",
            "X-FinMind-Delivery": str(delivery.id),
        }

        try:
            response = requests.post(
                target.url,
                data=payload_json,
                headers=headers,
                timeout=WebhookService.REQUEST_TIMEOUT_SECONDS,
            )
            delivery.response_status = response.status_code
            delivery.response_body = (response.text or "")[:2000]

            if response.status_code in WebhookService.SUCCESS_STATUS_CODES:
                delivery.status = "success"
                delivery.next_attempt_at = None
                result = "success"
            else:
                result = WebhookService._schedule_retry_or_fail(delivery)

        except requests.RequestException as exc:
            delivery.response_status = None
            delivery.response_body = str(exc)[:2000]
            result = WebhookService._schedule_retry_or_fail(delivery)

        db.session.commit()
        track_webhook_delivery_event(delivery.event_type, result)

    @staticmethod
    def redeliver(*, delivery_id: int, user_id: int) -> WebhookDelivery | None:
        delivery = (
            WebhookDelivery.query.join(
                WebhookTarget, WebhookTarget.id == WebhookDelivery.target_id
            )
            .filter(WebhookDelivery.id == delivery_id, WebhookTarget.user_id == user_id)
            .first()
        )
        if not delivery:
            return None
        delivery.status = "pending"
        delivery.next_attempt_at = datetime.utcnow()
        db.session.commit()
        track_webhook_delivery_event(delivery.event_type, "redeliver_requested")
        WebhookService.process_pending_deliveries(limit=1)
        return delivery

    @staticmethod
    def calculate_next_attempt(attempt_count: int) -> datetime:
        delay_seconds = min(60 * (2 ** max(attempt_count - 1, 0)), 3600)
        return datetime.utcnow() + timedelta(seconds=delay_seconds)

    @staticmethod
    def _normalize_event_name(event_type: WebhookEvent | str) -> str:
        if isinstance(event_type, WebhookEvent):
            return event_type.value
        event_name = str(event_type)
        if event_name not in {item.value for item in WebhookEvent}:
            raise ValueError("unsupported event type")
        return event_name

    @staticmethod
    def _normalize_events(events: list[str] | None) -> list[str]:
        all_events = [item.value for item in WebhookEvent]
        if events is None:
            return all_events
        if not isinstance(events, list) or len(events) == 0:
            raise ValueError("events must be a non-empty list")

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in events:
            value = str(raw).strip()
            if value == "*":
                return all_events
            if value not in all_events:
                raise ValueError(f"unsupported event type: {value}")
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _target_subscribed(target: WebhookTarget, event_name: str) -> bool:
        events = target.events or []
        if not isinstance(events, list):
            return False
        return event_name in events or "*" in events

    @staticmethod
    def _schedule_retry_or_fail(delivery: WebhookDelivery) -> str:
        if delivery.attempt_count <= WebhookService.MAX_RETRIES:
            delivery.status = "pending"
            delivery.next_attempt_at = WebhookService.calculate_next_attempt(
                delivery.attempt_count
            )
            return "retry_scheduled"
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = None
            return "failed"

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be a valid http(s) URL")
