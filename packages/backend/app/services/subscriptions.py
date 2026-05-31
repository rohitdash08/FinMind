from datetime import date, timedelta
from ..extensions import db
from ..models import DetectedSubscription, Expense
import logging

logger = logging.getLogger("finmind.subscriptions")


def detect_subscriptions(uid: int) -> list[dict]:
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=uid)
        .order_by(Expense.spent_at.desc())
        .all()
    )
    grouped: dict[str, list] = {}
    for e in expenses:
        key = (float(e.amount), e.notes or "")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(e)

    detected = []
    for (amount, notes), items in grouped.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: x.spent_at)
        intervals = []
        for i in range(1, len(items)):
            delta = (items[i].spent_at - items[i - 1].spent_at).days
            intervals.append(delta)
        if not intervals:
            continue
        avg_interval = sum(intervals) / len(intervals)
        if 25 <= avg_interval <= 35:
            interval = "MONTHLY"
        elif 7 <= avg_interval <= 10:
            interval = "WEEKLY"
        elif 355 <= avg_interval <= 375:
            interval = "YEARLY"
        else:
            continue

        existing = (
            db.session.query(DetectedSubscription)
            .filter_by(user_id=uid, name=notes, amount=amount)
            .first()
        )
        if existing:
            existing.last_detected = items[-1].spent_at
            db.session.commit()
            continue

        sub = DetectedSubscription(
            user_id=uid,
            name=notes or f"Subscription {amount}",
            amount=amount,
            currency=items[0].currency,
            interval=interval,
            category_id=items[0].category_id,
            last_detected=items[-1].spent_at,
        )
        db.session.add(sub)
        db.session.commit()
        detected.append(sub_to_dict(sub))

    logger.info("Detected subscriptions user=%s new=%s", uid, len(detected))
    return detected


def list_detected(uid: int) -> list[DetectedSubscription]:
    return (
        db.session.query(DetectedSubscription)
        .filter_by(user_id=uid, active=True)
        .order_by(DetectedSubscription.last_detected.desc())
        .all()
    )


def confirm_subscription(uid: int, sub_id: int) -> bool:
    sub = db.session.get(DetectedSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return False
    sub.confirmed = True
    db.session.commit()
    return True


def delete_subscription(uid: int, sub_id: int) -> bool:
    sub = db.session.get(DetectedSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return False
    db.session.delete(sub)
    db.session.commit()
    return True


def sub_to_dict(s: DetectedSubscription) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "amount": float(s.amount),
        "currency": s.currency,
        "interval": s.interval,
        "category_id": s.category_id,
        "last_detected": s.last_detected.isoformat(),
        "confirmed": s.confirmed,
        "active": s.active,
    }
