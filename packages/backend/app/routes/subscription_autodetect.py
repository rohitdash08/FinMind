"""
Auto-detect subscriptions from recurring charge patterns (#109).
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Expense
from ..services.subscription_autodetect import (
    ExpenseEntry,
    detect_from_expenses,
    detection_summary,
    KNOWN_SUBSCRIPTIONS,
)
import logging

bp = Blueprint("subscription_autodetect", __name__)
logger = logging.getLogger("finmind.subscription_autodetect")


def _load_expenses(user_id: int) -> list[ExpenseEntry]:
    """Load user expenses as ExpenseEntry objects."""
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=user_id)
        .all()
    )
    entries = []
    for exp in expenses:
        exp_date = exp.spent_at.date() if hasattr(exp.spent_at, "date") else exp.spent_at
        entries.append(ExpenseEntry(
            id=exp.id,
            amount=Decimal(str(exp.amount)),
            date=exp_date,
            description=exp.description or exp.notes or "",
            notes=exp.notes or "",
        ))
    return entries


@bp.get("")
@jwt_required()
def detect_subscriptions():
    """
    GET /api/subscriptions/detect
    Automatically detect subscription services from expense history.

    Query params:
      - lookback_days: int (default 365)
      - min_occurrences: int (default 2)
      - min_confidence: float (default 0.4)
    """
    uid = int(get_jwt_identity())
    lookback_days = int(request.args.get("lookback_days", 365))
    min_occurrences = int(request.args.get("min_occurrences", 2))
    min_confidence = float(request.args.get("min_confidence", 0.4))

    # Clamp params to safe values
    lookback_days = min(max(lookback_days, 30), 730)
    min_occurrences = min(max(min_occurrences, 1), 10)
    min_confidence = min(max(min_confidence, 0.0), 1.0)

    expenses = _load_expenses(uid)
    subscriptions = detect_from_expenses(
        expenses,
        min_occurrences=min_occurrences,
        lookback_days=lookback_days,
    )

    # Apply confidence filter
    if min_confidence > 0.4:
        subscriptions = [s for s in subscriptions if s.confidence >= min_confidence]

    logger.info("Subscription detection user=%s found=%s", uid, len(subscriptions))
    return jsonify({
        "subscriptions": [s.to_dict() for s in subscriptions],
        "summary": detection_summary(subscriptions),
    })


@bp.get("/known-services")
@jwt_required()
def list_known_services():
    """
    GET /api/subscriptions/detect/known-services
    Returns the list of known subscription service patterns.
    """
    services = sorted(set(KNOWN_SUBSCRIPTIONS.values()))
    return jsonify({
        "services": services,
        "total": len(services),
    })