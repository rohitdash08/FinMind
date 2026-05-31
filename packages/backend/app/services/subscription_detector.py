from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from ..extensions import db
from ..models import Expense, SubscriptionDetection, SubscriptionPriceSnapshot, PriceIncreaseAlert
import logging

logger = logging.getLogger("finmind.subscription_detector")


def detect_subscriptions(user_id: int) -> list[dict]:
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=user_id, expense_type="EXPENSE")
        .order_by(Expense.spent_at)
        .all()
    )
    merchant_groups = _group_by_merchant(expenses)
    detected = []
    for merchant, txns in merchant_groups.items():
        if len(txns) < 2:
            continue
        intervals = _compute_intervals(txns)
        if not intervals:
            continue
        avg_interval = sum(intervals) / len(intervals)
        interval_days = round(avg_interval)
        if interval_days < 20:
            continue
        amounts = sorted(set(float(t.amount) for t in txns))
        if not amounts:
            continue
        stable_amount = Decimal(str(amounts[-1]))
        existing = (
            db.session.query(SubscriptionDetection)
            .filter_by(user_id=user_id, merchant=merchant)
            .first()
        )
        if existing:
            existing.last_detected = txns[-1].spent_at
            existing.amount = stable_amount
            existing.interval_days = interval_days
            existing.status = "active"
        else:
            sub = SubscriptionDetection(
                user_id=user_id,
                merchant=merchant,
                amount=stable_amount,
                interval_days=interval_days,
                category=_infer_category(merchant),
                last_detected=txns[-1].spent_at,
            )
            db.session.add(sub)
            existing = sub
        db.session.flush()
        _record_price_snapshot(existing, txns)
        detected.append(_sub_to_dict(existing))
    db.session.commit()
    logger.info("Subscription detection user=%s found=%s", user_id, len(detected))
    return detected


def _group_by_merchant(expenses: list[Expense]) -> dict[str, list[Expense]]:
    groups: dict[str, list[Expense]] = defaultdict(list)
    for e in expenses:
        merchant = (e.notes or "").strip().lower()
        if not merchant:
            continue
        groups[merchant].append(e)
    return groups


def _compute_intervals(txns: list[Expense]) -> list[int]:
    intervals = []
    for i in range(1, len(txns)):
        gap = (txns[i].spent_at - txns[i - 1].spent_at).days
        if gap < 5:
            continue
        intervals.append(gap)
    return intervals


def _infer_category(merchant: str) -> str:
    kw = merchant.lower()
    if any(x in kw for x in ("netflix", "hulu", "disney", "spotify", "apple music", "youtube")):
        return "entertainment"
    if any(x in kw for x in ("aws", "google cloud", "azure", "digitalocean", "heroku")):
        return "cloud"
    if any(x in kw for x in ("dropbox", "google drive", "icloud", "onedrive")):
        return "storage"
    if any(x in kw for x in ("github", "gitlab", "slack", "notion", "figma")):
        return "productivity"
    if any(x in kw for x in ("gym", "fit", "strava", "peloton")):
        return "fitness"
    return "other"


def _record_price_snapshot(subscription: SubscriptionDetection, txns: list[Expense]):
    latest_amount = txns[-1].amount
    existing = (
        db.session.query(SubscriptionPriceSnapshot)
        .filter_by(
            subscription_id=subscription.id,
            amount=latest_amount,
            detected_at=txns[-1].spent_at,
        )
        .first()
    )
    if not existing:
        snap = SubscriptionPriceSnapshot(
            subscription_id=subscription.id,
            amount=latest_amount,
            detected_at=txns[-1].spent_at,
        )
        db.session.add(snap)


def _sub_to_dict(s: SubscriptionDetection) -> dict:
    return {
        "id": s.id,
        "merchant": s.merchant,
        "amount": float(s.amount),
        "interval_days": s.interval_days,
        "category": s.category or "other",
        "last_detected": s.last_detected.isoformat(),
        "status": s.status,
    }


def list_subscriptions(user_id: int, status: str | None = None) -> list[dict]:
    q = db.session.query(SubscriptionDetection).filter_by(user_id=user_id)
    if status:
        q = q.filter_by(status=status)
    subs = q.order_by(SubscriptionDetection.last_detected.desc()).all()
    return [_sub_to_dict(s) for s in subs]


def update_subscription(sub_id: int, user_id: int, data: dict) -> dict | None:
    sub = db.session.query(SubscriptionDetection).filter_by(id=sub_id, user_id=user_id).first()
    if not sub:
        return None
    if "status" in data:
        sub.status = data["status"]
    if "category" in data:
        sub.category = data["category"]
    db.session.commit()
    return _sub_to_dict(sub)


def get_price_history(sub_id: int, user_id: int) -> list[dict] | None:
    sub = db.session.query(SubscriptionDetection).filter_by(id=sub_id, user_id=user_id).first()
    if not sub:
        return None
    snapshots = (
        db.session.query(SubscriptionPriceSnapshot)
        .filter_by(subscription_id=sub.id)
        .order_by(SubscriptionPriceSnapshot.detected_at)
        .all()
    )
    return [
        {
            "id": s.id,
            "amount": float(s.amount),
            "detected_at": s.detected_at.isoformat(),
        }
        for s in snapshots
    ]


def check_price_increases(user_id: int) -> list[dict]:
    alerts = []
    subs = (
        db.session.query(SubscriptionDetection)
        .filter_by(user_id=user_id, status="active")
        .all()
    )
    for sub in subs:
        snapshots = (
            db.session.query(SubscriptionPriceSnapshot)
            .filter_by(subscription_id=sub.id)
            .order_by(SubscriptionPriceSnapshot.detected_at)
            .all()
        )
        if len(snapshots) < 2:
            continue
        old_amount = snapshots[-2].amount
        new_amount = snapshots[-1].amount
        if new_amount <= old_amount:
            continue
        increase_pct = ((new_amount - old_amount) / old_amount) * Decimal("100")
        existing = (
            db.session.query(PriceIncreaseAlert)
            .filter_by(
                user_id=user_id,
                subscription_id=sub.id,
                old_amount=old_amount,
                new_amount=new_amount,
                acknowledged=False,
            )
            .first()
        )
        if existing:
            continue
        alert = PriceIncreaseAlert(
            user_id=user_id,
            subscription_id=sub.id,
            old_amount=old_amount,
            new_amount=new_amount,
            increase_pct=increase_pct,
        )
        db.session.add(alert)
        db.session.flush()
        alerts.append({
            "id": alert.id,
            "subscription_id": sub.id,
            "merchant": sub.merchant,
            "old_amount": float(old_amount),
            "new_amount": float(new_amount),
            "increase_pct": float(increase_pct),
            "acknowledged": alert.acknowledged,
        })
    db.session.commit()
    return alerts
