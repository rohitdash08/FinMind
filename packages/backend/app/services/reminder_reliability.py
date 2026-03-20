"""
Reminder Reliability Tracking & Delivery Metrics Service (#123)

Tracks delivery success rates, latency, and failure analysis for reminders.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import defaultdict

from sqlalchemy import func, and_

from ..extensions import db
from ..models import ReminderDeliveryLog, Reminder


class ReminderReliabilityService:
    """Tracks and analyzes reminder delivery reliability metrics."""

    CHANNEL_WEIGHTS = {"email": 1.0, "sms": 0.9, "push": 0.85, "webhook": 0.95}

    def get_delivery_metrics(
        self,
        user_id: int,
        days: int = 30,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute overall delivery metrics for a user over the given window."""
        since = datetime.utcnow() - timedelta(days=days)
        query = db.session.query(ReminderDeliveryLog).filter(
            ReminderDeliveryLog.user_id == user_id,
            ReminderDeliveryLog.attempted_at >= since,
        )
        if channel:
            query = query.filter(ReminderDeliveryLog.channel == channel)

        logs: List[ReminderDeliveryLog] = query.all()
        if not logs:
            return {
                "total_attempts": 0,
                "success_rate": 1.0,
                "failure_rate": 0.0,
                "avg_latency_ms": None,
                "p95_latency_ms": None,
                "channels": {},
                "error_breakdown": {},
                "period_days": days,
            }

        total = len(logs)
        successes = [l for l in logs if l.status == "delivered"]
        failures = [l for l in logs if l.status == "failed"]
        success_rate = len(successes) / total if total else 1.0

        latencies = [
            l.latency_ms for l in logs if l.latency_ms is not None
        ]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        p95_latency = None
        if latencies:
            sorted_lat = sorted(latencies)
            idx = int(0.95 * len(sorted_lat))
            p95_latency = sorted_lat[min(idx, len(sorted_lat) - 1)]

        # Per-channel breakdown
        channel_stats: Dict[str, Dict] = defaultdict(
            lambda: {"attempts": 0, "delivered": 0, "failed": 0}
        )
        for l in logs:
            channel_stats[l.channel]["attempts"] += 1
            if l.status == "delivered":
                channel_stats[l.channel]["delivered"] += 1
            elif l.status == "failed":
                channel_stats[l.channel]["failed"] += 1

        for ch, stats in channel_stats.items():
            stats["success_rate"] = (
                stats["delivered"] / stats["attempts"]
                if stats["attempts"]
                else 1.0
            )

        # Error breakdown
        error_breakdown: Dict[str, int] = defaultdict(int)
        for l in failures:
            error_code = l.error_code or "unknown"
            error_breakdown[error_code] += 1

        return {
            "total_attempts": total,
            "success_rate": round(success_rate, 4),
            "failure_rate": round(1 - success_rate, 4),
            "avg_latency_ms": round(avg_latency, 2) if avg_latency else None,
            "p95_latency_ms": round(p95_latency, 2) if p95_latency else None,
            "channels": dict(channel_stats),
            "error_breakdown": dict(error_breakdown),
            "period_days": days,
        }

    def get_reminder_metrics(
        self, user_id: int, reminder_id: int
    ) -> Dict[str, Any]:
        """Per-reminder delivery history and reliability score."""
        reminder = db.session.get(Reminder, reminder_id)
        if not reminder or reminder.user_id != user_id:
            return {"error": "not_found"}

        logs: List[ReminderDeliveryLog] = (
            db.session.query(ReminderDeliveryLog)
            .filter_by(user_id=user_id, reminder_id=reminder_id)
            .order_by(ReminderDeliveryLog.attempted_at.desc())
            .all()
        )

        total = len(logs)
        delivered = sum(1 for l in logs if l.status == "delivered")
        reliability_score = delivered / total if total else 1.0
        last_attempt = logs[0].attempted_at.isoformat() if logs else None
        last_status = logs[0].status if logs else None

        return {
            "reminder_id": reminder_id,
            "message": reminder.message,
            "channel": reminder.channel,
            "total_attempts": total,
            "delivered_count": delivered,
            "failed_count": total - delivered,
            "reliability_score": round(reliability_score, 4),
            "last_attempt": last_attempt,
            "last_status": last_status,
            "delivery_history": [
                {
                    "attempted_at": l.attempted_at.isoformat(),
                    "status": l.status,
                    "latency_ms": l.latency_ms,
                    "error_code": l.error_code,
                    "retry_count": l.retry_count,
                }
                for l in logs[:20]
            ],
        }

    def get_failed_reminders(
        self, user_id: int, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List reminders with recent failures for retry."""
        logs = (
            db.session.query(ReminderDeliveryLog)
            .filter_by(user_id=user_id, status="failed")
            .order_by(ReminderDeliveryLog.attempted_at.desc())
            .limit(limit)
            .all()
        )
        seen: set = set()
        result = []
        for l in logs:
            if l.reminder_id not in seen:
                seen.add(l.reminder_id)
                result.append(
                    {
                        "reminder_id": l.reminder_id,
                        "channel": l.channel,
                        "error_code": l.error_code,
                        "last_failed_at": l.attempted_at.isoformat(),
                        "retry_count": l.retry_count,
                    }
                )
        return result

    def record_delivery_attempt(
        self,
        user_id: int,
        reminder_id: int,
        channel: str,
        status: str,
        latency_ms: Optional[float] = None,
        error_code: Optional[str] = None,
        retry_count: int = 0,
    ) -> ReminderDeliveryLog:
        """Record a delivery attempt and persist to DB."""
        log = ReminderDeliveryLog(
            user_id=user_id,
            reminder_id=reminder_id,
            channel=channel,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
            retry_count=retry_count,
            attempted_at=datetime.utcnow(),
        )
        db.session.add(log)
        db.session.commit()
        return log
