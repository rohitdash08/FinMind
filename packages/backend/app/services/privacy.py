from ..extensions import db
from ..models import (
    User, Category, Expense, RecurringExpense,
    Bill, Reminder, AdImpression, UserSubscription, AuditLog,
)
import logging

logger = logging.getLogger("finmind.privacy")


def export_user_data(user: User) -> dict:
    uid = user.id

    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    categories = db.session.query(Category).filter_by(user_id=uid).all()
    recurring = db.session.query(RecurringExpense).filter_by(user_id=uid).all()
    bills = db.session.query(Bill).filter_by(user_id=uid).all()
    reminders = db.session.query(Reminder).filter_by(user_id=uid).all()
    subscriptions = db.session.query(UserSubscription).filter_by(user_id=uid).all()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "created_at": user.created_at.isoformat(),
        },
        "categories": [
            {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
            for c in categories
        ],
        "expenses": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat(),
                "created_at": e.created_at.isoformat(),
            }
            for e in expenses
        ],
        "recurring_expenses": [
            {
                "id": r.id,
                "amount": float(r.amount),
                "currency": r.currency,
                "cadence": r.cadence.value,
                "notes": r.notes,
                "active": r.active,
            }
            for r in recurring
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value,
            }
            for b in bills
        ],
        "reminders": [
            {"id": r.id, "message": r.message, "send_at": r.send_at.isoformat(), "sent": r.sent}
            for r in reminders
        ],
        "subscriptions": [
            {"id": s.id, "plan_id": s.plan_id, "active": s.active}
            for s in subscriptions
        ],
    }


def delete_user_data(uid: int) -> None:
    # Delete in dependency order (children first)
    db.session.query(Reminder).filter_by(user_id=uid).delete()
    db.session.query(UserSubscription).filter_by(user_id=uid).delete()
    db.session.query(AdImpression).filter_by(user_id=uid).delete()
    db.session.query(Bill).filter_by(user_id=uid).delete()
    db.session.query(Expense).filter_by(user_id=uid).delete()
    db.session.query(RecurringExpense).filter_by(user_id=uid).delete()
    db.session.query(Category).filter_by(user_id=uid).delete()
    # Audit logs are retained for compliance (user_id set to None)
    db.session.query(AuditLog).filter_by(user_id=uid).update({"user_id": None})
    # Finally delete the user record
    db.session.query(User).filter_by(id=uid).delete()
    db.session.flush()
    logger.info("Deleted all PII for user_id=%s", uid)