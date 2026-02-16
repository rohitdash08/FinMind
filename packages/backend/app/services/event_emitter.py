"""Lightweight event emitter that dispatches events to registered webhooks.

Usage in routes:
    from ..services.event_emitter import emit

    # After creating an expense:
    emit(user_id, "expense.created", {"id": e.id, "amount": float(e.amount)})

Events are dispatched asynchronously by delegating to the webhook service.
If no webhooks are registered, this is a no-op.
"""

import logging
from typing import Any

logger = logging.getLogger("finmind.events")


def emit(user_id: int, event_type: str, data: dict[str, Any]) -> list[int]:
    """Emit an event for a user. Returns delivery IDs (empty if no webhooks)."""
    try:
        from .webhooks import emit_event
        delivery_ids = emit_event(user_id, event_type, data)
        if delivery_ids:
            logger.info(
                "Event emitted type=%s user=%s deliveries=%s",
                event_type, user_id, len(delivery_ids),
            )
        return delivery_ids
    except Exception:
        # Never let webhook failures break the main operation
        logger.exception("Event emission failed type=%s user=%s", event_type, user_id)
        return []
