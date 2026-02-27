"""Smart reminder timing optimization.

Learns from user behavior patterns (when they pay bills, check the app)
to suggest optimal reminder times instead of fixed schedules.
"""

from datetime import datetime, date, timedelta, time
from collections import defaultdict
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Bill


class ReminderPreference(db.Model):
    __tablename__ = "reminder_preferences"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    preferred_hour = db.Column(db.Integer, default=9)  # 0-23
    preferred_day_offset = db.Column(db.Integer, default=3)  # days before due
    auto_optimize = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_preference(user_id: int) -> dict:
    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        return {"preferred_hour": 9, "preferred_day_offset": 3, "auto_optimize": True, "is_default": True}
    return {
        "id": pref.id,
        "preferred_hour": pref.preferred_hour,
        "preferred_day_offset": pref.preferred_day_offset,
        "auto_optimize": pref.auto_optimize,
        "is_default": False,
    }


def update_preference(user_id: int, hour: int | None = None, day_offset: int | None = None, auto_optimize: bool | None = None) -> dict:
    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        pref = ReminderPreference(user_id=user_id)
        db.session.add(pref)
    if hour is not None:
        pref.preferred_hour = max(0, min(23, hour))
    if day_offset is not None:
        pref.preferred_day_offset = max(0, min(30, day_offset))
    if auto_optimize is not None:
        pref.auto_optimize = auto_optimize
    db.session.commit()
    return get_preference(user_id)


def analyze_payment_patterns(user_id: int) -> dict:
    """Analyze when the user typically makes payments relative to bill due dates."""
    bills = Bill.query.filter_by(user_id=user_id).all()
    if not bills:
        return {"pattern": "no_data", "suggestions": []}

    # Analyze expense timing patterns
    expenses = (
        db.session.query(Expense.date, func.count(Expense.id))
        .filter(Expense.user_id == user_id)
        .group_by(Expense.date)
        .all()
    )

    if not expenses:
        return {"pattern": "no_data", "suggestions": []}

    # Day-of-week activity
    dow_counts = defaultdict(int)
    for exp_date, count in expenses:
        dow_counts[exp_date.weekday()] += count

    # Find most active days
    total = sum(dow_counts.values())
    dow_pcts = {d: round(c / total * 100, 1) for d, c in dow_counts.items()} if total else {}
    peak_day = max(dow_counts, key=dow_counts.get) if dow_counts else 0

    # Day-of-month patterns
    dom_counts = defaultdict(int)
    for exp_date, count in expenses:
        dom_counts[exp_date.day] += count

    # Cluster into early/mid/late month
    early = sum(dom_counts.get(d, 0) for d in range(1, 11))
    mid = sum(dom_counts.get(d, 0) for d in range(11, 21))
    late = sum(dom_counts.get(d, 0) for d in range(21, 32))

    if early >= mid and early >= late:
        month_pattern = "early_month"
    elif mid >= early and mid >= late:
        month_pattern = "mid_month"
    else:
        month_pattern = "late_month"

    suggestions = _generate_suggestions(peak_day, month_pattern, bills)

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    return {
        "pattern": month_pattern,
        "peak_activity_day": day_names[peak_day],
        "day_of_week_distribution": {day_names[d]: p for d, p in dow_pcts.items()},
        "suggestions": suggestions,
        "bills_analyzed": len(bills),
        "expenses_analyzed": total,
    }


def optimize_reminders(user_id: int) -> dict:
    """Auto-optimize reminder settings based on patterns."""
    patterns = analyze_payment_patterns(user_id)
    if patterns["pattern"] == "no_data":
        return {"optimized": False, "reason": "insufficient_data", "preference": get_preference(user_id)}

    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    if pref and not pref.auto_optimize:
        return {"optimized": False, "reason": "auto_optimize_disabled", "preference": get_preference(user_id)}

    # Pick best suggestion
    if patterns["suggestions"]:
        best = patterns["suggestions"][0]
        updated = update_preference(user_id, hour=best.get("hour", 9), day_offset=best.get("day_offset", 3))
        return {"optimized": True, "applied": best, "preference": updated, "patterns": patterns}

    return {"optimized": False, "reason": "no_improvements_found", "preference": get_preference(user_id)}


def suggest_reminder_time(user_id: int, due_date: date) -> dict:
    """Suggest the best reminder time for a specific due date."""
    pref = get_preference(user_id)
    remind_date = due_date - timedelta(days=pref["preferred_day_offset"])

    # Don't remind in the past
    if remind_date < date.today():
        remind_date = date.today()

    remind_time = time(hour=pref["preferred_hour"])

    return {
        "due_date": due_date.isoformat(),
        "suggested_remind_date": remind_date.isoformat(),
        "suggested_remind_time": remind_time.isoformat(),
        "day_offset": pref["preferred_day_offset"],
    }


def _generate_suggestions(peak_day: int, month_pattern: str, bills: list) -> list[dict]:
    suggestions = []

    # Suggest reminder hour based on pattern
    if month_pattern == "early_month":
        suggestions.append({
            "type": "timing",
            "description": "You're most active early in the month. Set reminders for the 1st-5th.",
            "hour": 9,
            "day_offset": 5,
            "confidence": "medium",
        })
    elif month_pattern == "late_month":
        suggestions.append({
            "type": "timing",
            "description": "You tend to pay later in the month. Earlier reminders may help.",
            "hour": 10,
            "day_offset": 7,
            "confidence": "medium",
        })

    # Weekend vs weekday
    if peak_day >= 5:
        suggestions.append({
            "type": "day_preference",
            "description": "You're more active on weekends. Consider weekend reminders.",
            "hour": 10,
            "confidence": "low",
        })
    else:
        suggestions.append({
            "type": "day_preference",
            "description": "Weekday mornings seem to be your active time.",
            "hour": 8,
            "confidence": "low",
        })

    return suggestions
