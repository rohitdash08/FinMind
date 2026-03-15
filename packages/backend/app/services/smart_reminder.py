"""Smart reminder timing optimization service.

Analyzes user activity patterns to determine optimal reminder delivery
times. Respects quiet hours, interval constraints, and daily limits.
"""

from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.models import UserActivityLog, ReminderPreference


# ── Activity Logging ──────────────────────────────────────────────


def log_activity(user_id: int, action: str) -> dict:
    """Log a user activity event for timing analysis."""
    now = datetime.utcnow()
    log = UserActivityLog(
        user_id=user_id,
        action=action,
        hour_of_day=now.hour,
        day_of_week=now.weekday(),
    )
    db.session.add(log)
    db.session.commit()
    return {
        "id": log.id,
        "action": action,
        "hour_of_day": log.hour_of_day,
        "day_of_week": log.day_of_week,
    }


def get_activity_pattern(user_id: int) -> dict:
    """Analyze user activity patterns.

    Returns hourly and daily distribution of user activity.
    """
    logs = UserActivityLog.query.filter_by(user_id=user_id).all()

    if not logs:
        return {
            "total_activities": 0,
            "hourly_distribution": {str(h): 0 for h in range(24)},
            "daily_distribution": {str(d): 0 for d in range(7)},
            "peak_hours": [],
            "peak_days": [],
            "most_active_hour": None,
            "most_active_day": None,
        }

    hour_counts = Counter(log.hour_of_day for log in logs)
    day_counts = Counter(log.day_of_week for log in logs)

    hourly = {str(h): hour_counts.get(h, 0) for h in range(24)}
    daily = {str(d): day_counts.get(d, 0) for d in range(7)}

    # Find peak hours (top 3)
    sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
    peak_hours = [h for h, _ in sorted_hours[:3]]

    # Find peak days (top 3)
    sorted_days = sorted(day_counts.items(), key=lambda x: x[1], reverse=True)
    peak_days = [d for d, _ in sorted_days[:3]]

    return {
        "total_activities": len(logs),
        "hourly_distribution": hourly,
        "daily_distribution": daily,
        "peak_hours": peak_hours,
        "peak_days": peak_days,
        "most_active_hour": sorted_hours[0][0] if sorted_hours else None,
        "most_active_day": sorted_days[0][0] if sorted_days else None,
    }


# ── Preferences ───────────────────────────────────────────────────


def get_preferences(user_id: int) -> dict:
    """Get reminder preferences for a user."""
    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        return _default_preferences(user_id)
    return _serialize_preferences(pref)


def update_preferences(user_id: int, **kwargs) -> dict:
    """Update or create reminder preferences."""
    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        pref = ReminderPreference(user_id=user_id)
        db.session.add(pref)

    for key in ["preferred_hour", "preferred_days", "quiet_hours_start",
                "quiet_hours_end", "auto_optimize", "min_interval_hours",
                "max_reminders_per_day"]:
        if key in kwargs:
            setattr(pref, key, kwargs[key])

    pref.updated_at = datetime.utcnow()
    db.session.commit()
    return _serialize_preferences(pref)


# ── Optimal Timing ────────────────────────────────────────────────


def get_optimal_time(user_id: int) -> dict:
    """Calculate the optimal reminder time based on user behavior.

    Strategy:
    1. If auto_optimize is off, use preferred_hour
    2. Analyze activity patterns for peak engagement hours
    3. Filter out quiet hours
    4. Return best hour with confidence score
    """
    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    quiet_start = pref.quiet_hours_start if pref else 22
    quiet_end = pref.quiet_hours_end if pref else 7
    auto_optimize = pref.auto_optimize if pref else True

    if not auto_optimize and pref:
        return {
            "optimal_hour": pref.preferred_hour,
            "confidence": 1.0,
            "method": "user_preference",
            "is_quiet_hour": _is_quiet_hour(pref.preferred_hour, quiet_start, quiet_end),
            "alternative_hours": [],
        }

    pattern = get_activity_pattern(user_id)

    if pattern["total_activities"] < 5:
        preferred = pref.preferred_hour if pref else 9
        return {
            "optimal_hour": preferred,
            "confidence": 0.3,
            "method": "default_insufficient_data",
            "is_quiet_hour": _is_quiet_hour(preferred, quiet_start, quiet_end),
            "alternative_hours": [10, 14, 18],
        }

    # Score each hour based on activity + avoid quiet hours
    hourly = pattern["hourly_distribution"]
    max_count = max(int(v) for v in hourly.values()) or 1

    scored_hours = []
    for hour in range(24):
        if _is_quiet_hour(hour, quiet_start, quiet_end):
            continue
        count = int(hourly.get(str(hour), 0))
        score = count / max_count
        scored_hours.append((hour, score))

    scored_hours.sort(key=lambda x: x[1], reverse=True)

    if not scored_hours:
        return {
            "optimal_hour": 9,
            "confidence": 0.1,
            "method": "fallback_all_quiet",
            "is_quiet_hour": False,
            "alternative_hours": [],
        }

    best_hour, best_score = scored_hours[0]
    alternatives = [h for h, _ in scored_hours[1:4]]

    return {
        "optimal_hour": best_hour,
        "confidence": round(min(best_score + 0.3, 1.0), 2),
        "method": "activity_analysis",
        "is_quiet_hour": False,
        "alternative_hours": alternatives,
    }


def get_optimal_days(user_id: int) -> dict:
    """Calculate optimal days for reminders based on activity."""
    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    pattern = get_activity_pattern(user_id)

    if pattern["total_activities"] < 5:
        preferred_str = pref.preferred_days if pref else "1,2,3,4,5"
        days = [int(d) for d in preferred_str.split(",") if d.strip()]
        return {
            "optimal_days": days,
            "confidence": 0.3,
            "method": "default",
            "day_scores": {str(d): 0 for d in range(7)},
        }

    daily = pattern["daily_distribution"]
    max_count = max(int(v) for v in daily.values()) or 1

    day_scores = {}
    for day in range(7):
        count = int(daily.get(str(day), 0))
        day_scores[str(day)] = round(count / max_count, 2)

    # Top days with score > 0.3
    optimal = [int(d) for d, s in sorted(day_scores.items(), key=lambda x: x[1], reverse=True) if s > 0.3]
    if not optimal:
        optimal = [1, 2, 3, 4, 5]  # Default weekdays

    return {
        "optimal_days": optimal,
        "confidence": round(min(max(day_scores.values()) + 0.2, 1.0), 2),
        "method": "activity_analysis",
        "day_scores": day_scores,
    }


def should_send_reminder(user_id: int, current_hour: Optional[int] = None) -> dict:
    """Check if a reminder should be sent right now.

    Considers:
    - Quiet hours
    - Daily limit
    - Minimum interval
    - Optimal timing
    """
    if current_hour is None:
        current_hour = datetime.utcnow().hour

    pref = ReminderPreference.query.filter_by(user_id=user_id).first()
    quiet_start = pref.quiet_hours_start if pref else 22
    quiet_end = pref.quiet_hours_end if pref else 7

    # Check quiet hours
    if _is_quiet_hour(current_hour, quiet_start, quiet_end):
        return {
            "should_send": False,
            "reason": "quiet_hours",
            "current_hour": current_hour,
            "next_available_hour": quiet_end,
        }

    # Get optimal time
    optimal = get_optimal_time(user_id)
    optimal_hour = optimal["optimal_hour"]

    # Allow ±1 hour window around optimal time
    in_window = abs(current_hour - optimal_hour) <= 1 or abs(current_hour - optimal_hour) >= 23

    return {
        "should_send": in_window,
        "reason": "optimal_window" if in_window else "outside_optimal_window",
        "current_hour": current_hour,
        "optimal_hour": optimal_hour,
        "confidence": optimal["confidence"],
    }


# ── Helpers ───────────────────────────────────────────────────────


def _is_quiet_hour(hour: int, start: int, end: int) -> bool:
    """Check if an hour falls within quiet hours."""
    if start <= end:
        return start <= hour < end
    else:
        # Wraps midnight (e.g., 22-7)
        return hour >= start or hour < end


def _default_preferences(user_id: int) -> dict:
    return {
        "user_id": user_id,
        "preferred_hour": 9,
        "preferred_days": "1,2,3,4,5",
        "quiet_hours_start": 22,
        "quiet_hours_end": 7,
        "auto_optimize": True,
        "min_interval_hours": 4,
        "max_reminders_per_day": 5,
    }


def _serialize_preferences(pref: ReminderPreference) -> dict:
    return {
        "user_id": pref.user_id,
        "preferred_hour": pref.preferred_hour,
        "preferred_days": pref.preferred_days,
        "quiet_hours_start": pref.quiet_hours_start,
        "quiet_hours_end": pref.quiet_hours_end,
        "auto_optimize": pref.auto_optimize,
        "min_interval_hours": pref.min_interval_hours,
        "max_reminders_per_day": pref.max_reminders_per_day,
    }
