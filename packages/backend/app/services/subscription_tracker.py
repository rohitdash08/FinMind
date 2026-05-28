"""Subscription & Recurring Payment Tracker.

Track and manage subscriptions:
- Subscription CRUD (name, amount, billing cycle, category)
- Renewal date tracking and alerts
- Annual cost projection
- Category grouping and analysis
- Usage tracking (used vs paid)
- Free trial tracking with auto-conversion alerts
- Optimization suggestions (unused subscriptions)
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.subscription")


class BillingCycle(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    TRIAL = "trial"


CYCLE_MULTIPLIER = {
    "weekly": 52,
    "monthly": 12,
    "quarterly": 4,
    "yearly": 1,
}


class Subscription:
    def __init__(self, sub_id: str, name: str, amount: float,
                 cycle: str, category: str = "other",
                 start_date: str = None, status: str = "active",
                 is_trial: bool = False, trial_end: str = None,
                 notes: str = ""):
        self.sub_id = sub_id
        self.name = name
        self.amount = amount
        self.cycle = cycle
        self.category = category
        self.start_date = start_date or datetime.utcnow().isoformat()[:10]
        self.status = status
        self.is_trial = is_trial
        self.trial_end = trial_end
        self.notes = notes
        self.usage_log = []  # [{date, used: bool}]
        self.payments = []   # [{date, amount}]

    @property
    def annual_cost(self) -> float:
        return self.amount * CYCLE_MULTIPLIER.get(self.cycle, 12)

    @property
    def monthly_cost(self) -> float:
        return self.annual_cost / 12

    @property
    def next_billing_date(self) -> str:
        """Calculate next billing date."""
        start = datetime.fromisoformat(self.start_date[:10])
        if self.cycle == "weekly":
            next_date = start + timedelta(weeks=1)
        elif self.cycle == "monthly":
            next_date = start + timedelta(days=30)
        elif self.cycle == "quarterly":
            next_date = start + timedelta(days=90)
        elif self.cycle == "yearly":
            next_date = start + timedelta(days=365)
        else:
            next_date = start + timedelta(days=30)

        # If next date is in the past, project forward
        now = datetime.utcnow()
        while next_date < now:
            if self.cycle == "weekly":
                next_date += timedelta(weeks=1)
            elif self.cycle == "monthly":
                next_date += timedelta(days=30)
            elif self.cycle == "quarterly":
                next_date += timedelta(days=90)
            elif self.cycle == "yearly":
                next_date += timedelta(days=365)
            else:
                next_date += timedelta(days=30)

        return next_date.isoformat()[:10]

    def to_dict(self):
        return {
            "sub_id": self.sub_id,
            "name": self.name,
            "amount": round(self.amount, 2),
            "cycle": self.cycle,
            "category": self.category,
            "start_date": self.start_date,
            "status": self.status,
            "is_trial": self.is_trial,
            "trial_end": self.trial_end,
            "notes": self.notes,
            "annual_cost": round(self.annual_cost, 2),
            "monthly_cost": round(self.monthly_cost, 2),
            "next_billing": self.next_billing_date,
            "payment_count": len(self.payments),
        }


class SubscriptionTracker:
    """Track and analyze subscriptions."""

    def __init__(self):
        self.subscriptions = {}  # sub_id -> Subscription
        self.user_subs = defaultdict(list)  # user_id -> [sub_ids]

    def add(self, user_id: str, name: str, amount: float, cycle: str,
             category: str = "other", start_date: str = None,
             is_trial: bool = False, trial_end: str = None,
             notes: str = "") -> dict:
        """Add a new subscription."""
        sub_id = str(uuid4())[:8]
        status = "trial" if is_trial else "active"
        sub = Subscription(
            sub_id=sub_id, name=name, amount=amount, cycle=cycle,
            category=category, start_date=start_date, status=status,
            is_trial=is_trial, trial_end=trial_end, notes=notes,
        )
        self.subscriptions[sub_id] = sub
        self.user_subs[user_id].append(sub_id)
        return sub.to_dict()

    def update(self, sub_id: str, **kwargs) -> dict:
        """Update a subscription."""
        if sub_id not in self.subscriptions:
            return {"error": "Subscription not found"}

        sub = self.subscriptions[sub_id]
        for key, value in kwargs.items():
            if hasattr(sub, key):
                setattr(sub, key, value)
        return sub.to_dict()

    def cancel(self, sub_id: str) -> dict:
        """Cancel a subscription."""
        return self.update(sub_id, status="cancelled")

    def pause(self, sub_id: str) -> dict:
        """Pause a subscription."""
        return self.update(sub_id, status="paused")

    def resume(self, sub_id: str) -> dict:
        """Resume a paused subscription."""
        return self.update(sub_id, status="active")

    def record_usage(self, sub_id: str, used: bool = True) -> dict:
        """Record whether the subscription was used."""
        if sub_id not in self.subscriptions:
            return {"error": "Subscription not found"}
        self.subscriptions[sub_id].usage_log.append({
            "date": datetime.utcnow().isoformat()[:10],
            "used": used,
        })
        return {"status": "recorded"}

    def record_payment(self, sub_id: str, amount: float = None) -> dict:
        """Record a payment for a subscription."""
        if sub_id not in self.subscriptions:
            return {"error": "Not found"}
        sub = self.subscriptions[sub_id]
        sub.payments.append({
            "date": datetime.utcnow().isoformat()[:10],
            "amount": amount or sub.amount,
        })
        return {"status": "recorded"}

    def get_summary(self, user_id: str) -> dict:
        """Get subscription summary for a user."""
        sub_ids = self.user_subs.get(user_id, [])
        subs = [self.subscriptions[sid] for sid in sub_ids
                if sid in self.subscriptions]

        active = [s for s in subs if s.status == "active"]
        total_monthly = sum(s.monthly_cost for s in active)
        total_annual = sum(s.annual_cost for s in active)

        # Category breakdown
        by_category = defaultdict(float)
        for s in active:
            by_category[s.category] += s.monthly_cost

        # Trial ending soon
        now = datetime.utcnow()
        trials_ending = []
        for s in subs:
            if s.is_trial and s.trial_end:
                trial_end_date = datetime.fromisoformat(s.trial_end[:10])
                days_left = (trial_end_date - now).days
                if 0 <= days_left <= 7:
                    trials_ending.append({
                        "name": s.name,
                        "trial_end": s.trial_end,
                        "days_left": days_left,
                        "amount": s.amount,
                    })

        # Usage analysis (unused subscriptions)
        unused = []
        for s in active:
            if s.usage_log:
                recent = s.usage_log[-4:]  # Last 4 entries
                usage_rate = sum(1 for u in recent if u["used"]) / len(recent)
                if usage_rate < 0.25:
                    unused.append({
                        "name": s.name,
                        "monthly_cost": round(s.monthly_cost, 2),
                        "usage_rate": round(usage_rate * 100, 1),
                    })

        return {
            "total_active": len(active),
            "total_monthly": round(total_monthly, 2),
            "total_annual": round(total_annual, 2),
            "by_category": {k: round(v, 2) for k, v in
                           sorted(by_category.items(), key=lambda x: x[1], reverse=True)},
            "trials_ending_soon": trials_ending,
            "potentially_unused": unused,
            "potential_savings": round(sum(u["monthly_cost"] for u in unused) * 12, 2),
        }

    def get_upcoming(self, user_id: str, days: int = 30) -> list[dict]:
        """Get upcoming billing dates."""
        sub_ids = self.user_subs.get(user_id, [])
        now = datetime.utcnow()
        upcoming = []

        for sid in sub_ids:
            if sid not in self.subscriptions:
                continue
            sub = self.subscriptions[sid]
            if sub.status != "active":
                continue

            next_billing = datetime.fromisoformat(sub.next_billing_date)
            days_until = (next_billing - now).days

            if 0 <= days_until <= days:
                upcoming.append({
                    **sub.to_dict(),
                    "days_until_billing": days_until,
                })

        return sorted(upcoming, key=lambda x: x["days_until_billing"])

    def get_all(self, user_id: str, status: str = None) -> list[dict]:
        """Get all subscriptions, optionally filtered by status."""
        sub_ids = self.user_subs.get(user_id, [])
        subs = [self.subscriptions[sid].to_dict()
                for sid in sub_ids if sid in self.subscriptions]
        if status:
            subs = [s for s in subs if s["status"] == status]
        return subs
