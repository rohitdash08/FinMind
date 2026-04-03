"""
Subscription cost increase detection endpoints (#110).
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import and_

from ..extensions import db
from ..models import RecurringExpense, Expense
from ..services.subscription_detect import (
    SubscriptionConfig,
    ChargeRecord,
    detect_price_increase,
    detect_vs_expected,
    scan_all_subscriptions,
    price_change_summary,
)
import logging

bp = Blueprint("subscription_detect", __name__)
logger = logging.getLogger("finmind.subscription_detect")


def _load_subscription_configs(user_id: int, sub_id: int | None = None) -> list[SubscriptionConfig]:
    """Load RecurringExpenses as SubscriptionConfig objects."""
    q = db.session.query(RecurringExpense).filter_by(user_id=user_id, active=True)
    if sub_id is not None:
        q = q.filter_by(id=sub_id)
    configs = []
    for rec in q.all():
        configs.append(SubscriptionConfig(
            id=rec.id,
            name=rec.notes or f"Subscription #{rec.id}",
            expected_amount=Decimal(str(rec.amount)),
            cadence=rec.cadence.value if hasattr(rec.cadence, "value") else rec.cadence,
            currency=rec.currency or "USD",
            active=rec.active,
        ))
    return configs


def _load_charge_records(user_id: int, recurring_id: int | None = None) -> dict[int, list[ChargeRecord]]:
    """Load expense charges grouped by source_recurring_id."""
    q = (
        db.session.query(Expense)
        .filter_by(user_id=user_id)
        .filter(Expense.source_recurring_id.isnot(None))
    )
    if recurring_id is not None:
        q = q.filter_by(source_recurring_id=recurring_id)

    by_id: dict[int, list[ChargeRecord]] = {}
    for exp in q.all():
        rid = exp.source_recurring_id
        charge_date = exp.spent_at.date() if hasattr(exp.spent_at, "date") else exp.spent_at
        by_id.setdefault(rid, []).append(
            ChargeRecord(
                id=exp.id,
                amount=Decimal(str(exp.amount)),
                charge_date=charge_date,
                subscription_id=rid,
            )
        )
    return by_id


@bp.get("")
@jwt_required()
def list_price_changes():
    """
    GET /api/subscriptions/price-changes
    Scan all active subscriptions for price increases.

    Query params:
      - severity: info|medium|high (filter)
    """
    uid = int(get_jwt_identity())
    severity_filter = request.args.get("severity")

    configs = _load_subscription_configs(uid)
    if not configs:
        return jsonify({
            "alerts": [],
            "summary": price_change_summary([]),
        })

    charges_map = _load_charge_records(uid)
    alerts = scan_all_subscriptions(configs, charges_map)

    if severity_filter:
        alerts = [a for a in alerts if a.severity == severity_filter]

    logger.info("Subscription price scan user=%s alerts=%s", uid, len(alerts))
    return jsonify({
        "alerts": [a.to_dict() for a in alerts],
        "summary": price_change_summary(alerts),
    })


@bp.get("/<int:subscription_id>")
@jwt_required()
def get_price_changes_for_subscription(subscription_id: int):
    """
    GET /api/subscriptions/price-changes/<subscription_id>
    Check price changes for a specific subscription.
    """
    uid = int(get_jwt_identity())

    configs = _load_subscription_configs(uid, sub_id=subscription_id)
    if not configs:
        return jsonify(error="Subscription not found"), 404

    config = configs[0]
    charges_map = _load_charge_records(uid, recurring_id=subscription_id)
    charges = charges_map.get(subscription_id, [])

    alerts = detect_price_increase(config, charges)

    latest = sorted(charges, key=lambda c: c.charge_date)[-1] if charges else None
    vs_expected = detect_vs_expected(config, latest)
    if vs_expected:
        already_found = any(a.affected_charge_id == vs_expected.affected_charge_id for a in alerts)
        if not already_found:
            alerts.append(vs_expected)

    return jsonify({
        "subscription_id": subscription_id,
        "subscription_name": config.name,
        "current_expected_amount": str(config.expected_amount),
        "alerts": [a.to_dict() for a in alerts],
        "summary": price_change_summary(alerts),
        "charge_count_analyzed": len(charges),
    })