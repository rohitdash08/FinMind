"""
Celery tasks for async webhook operations

Provides:
- Webhook retry logic
- Batch webhook delivery
"""

import logging
from celery import Celery, Task
from .extensions import db
from .models import Webhook, WebhookDelivery, WebhookDeliveryStatus
from .services.webhooks import webhook_service

logger = logging.getLogger("finmind.webhooks")

# Celery instance
celery_app = Celery('finmind')


class DatabaseTask(Task):
    """Base task with database session management"""
    _db = None

    @property
    def db(self):
        if self._db is None:
            self._db = db
        return self._db


def retry_webhook_delivery(delivery_id: int) -> bool:
    """
    Retry a failed webhook delivery

    This task is scheduled by the webhook service when a delivery fails.
    It attempts to redeliver the webhook with exponential backoff.

    Args:
        delivery_id: The ID of the WebhookDelivery record

    Returns:
        bool: True if delivery succeeded, False otherwise
    """
    delivery = None
    try:
        # Get the delivery record
        delivery = db.session.get(WebhookDelivery, delivery_id)
        if not delivery:
            logger.error(f"Delivery not found: {delivery_id}")
            return False

        logger.info(
            f"Retrying webhook delivery: id={delivery_id}, "
            f"webhook_id={delivery.webhook_id}, "
            f"event={delivery.event_type}, "
            f"attempt={delivery.retry_count}"
        )

        # Check if webhook still exists and is active
        webhook = db.session.get(Webhook, delivery.webhook_id)
        if not webhook or not webhook.active:
            logger.warning(
                f"Webhook not found or inactive: webhook_id={delivery.webhook_id}, "
                f"stopping retry for delivery={delivery_id}"
            )
            delivery.status = WebhookDeliveryStatus.FAILED.value
            db.session.commit()
            return False

        # Get the original payload
        payload_data = delivery.payload or {}
        from .services.webhooks import WebhookPayload, WebhookEventType
        payload = WebhookPayload(
            event_type=WebhookEventType(payload_data.get("event_type")),
            data=payload_data.get("data", {}),
            timestamp=payload_data.get("timestamp", 0),
            user_id=None,
            idempotency_key=payload_data.get("idempotency_key"),
            trace_id=payload_data.get("trace_id")
        )

        # Deliver the webhook
        success = webhook_service._deliver_single_webhook(webhook, payload)

        if success:
            # Update delivery record
            delivery.status = WebhookDeliveryStatus.SENT.value
            delivery.last_attempt_at = delivery.last_attempt_at or None
            db.session.commit()
            logger.info(f"Webhook retry succeeded: delivery_id={delivery_id}")
        else:
            # Update delivery record
            delivery.status = WebhookDeliveryStatus.FAILED.value
            db.session.commit()
            logger.error(f"Webhook retry failed: delivery_id={delivery_id}")

        return success

    except Exception as e:
        logger.error(
            f"Error in retry_webhook_delivery: delivery_id={delivery_id}, "
            f"error={str(e)}",
            exc_info=True
        )
        try:
            if delivery:
                delivery.status = WebhookDeliveryStatus.FAILED.value
                db.session.commit()
        except Exception as commit_error:
            logger.error(f"Error updating delivery status: {commit_error}", exc_info=True)
        return False


@celery_app.task(name="deliver_webhooks_batch", base=DatabaseTask, bind=True)
def deliver_webhooks_batch(self, webhook_ids: list, event_type: str, data: dict, user_id: int):
    """
    Deliver webhooks to multiple endpoints in batch

    This is useful for high-volume scenarios where you want to deliver
    the same event to multiple webhooks asynchronously.

    Args:
        webhook_ids: List of webhook IDs to deliver to
        event_type: Event type string
        data: Event payload data
        user_id: User ID for the event

    Returns:
        dict: Summary of delivery results
    """
    from .services.webhooks import WebhookPayload, WebhookEventType

    logger.info(
        f"Batch webhook delivery: count={len(webhook_ids)}, "
        f"event={event_type}, user_id={user_id}"
    )

    results = {
        "total": len(webhook_ids),
        "success": 0,
        "failed": 0,
        "details": []
    }

    for webhook_id in webhook_ids:
        try:
            webhook = db.session.get(Webhook, webhook_id)
            if not webhook or not webhook.active:
                logger.debug(f"Skipping inactive webhook: {webhook_id}")
                continue

            payload = WebhookPayload(
                event_type=WebhookEventType(event_type),
                data=data,
                timestamp=webhook_service._generate_trace_id() or 0,
                user_id=user_id,
                idempotency_key=webhook_service._generate_idempotency_key(
                    WebhookEventType(event_type), user_id
                ),
                trace_id=webhook_service._generate_trace_id()
            )

            success = webhook_service._deliver_single_webhook(webhook, payload)
            if success:
                results["success"] += 1
                results["details"].append({"webhook_id": webhook_id, "status": "success"})
            else:
                results["failed"] += 1
                results["details"].append({"webhook_id": webhook_id, "status": "failed"})

        except Exception as e:
            logger.error(
                f"Error delivering webhook in batch: webhook_id={webhook_id}, "
                f"error={str(e)}",
                exc_info=True
            )
            results["failed"] += 1
            results["details"].append({
                "webhook_id": webhook_id,
                "status": "error",
                "error": str(e)
            })

    logger.info(
        f"Batch webhook delivery complete: total={results['total']}, "
        f"success={results['success']}, failed={results['failed']}"
    )

    return results
