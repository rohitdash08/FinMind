"""Bill Reminder & Due Date Manager.

Never miss a bill:
- Bill creation with due dates, amounts, recurrence
- Multi-frequency support (one-time, weekly, monthly, yearly)
- Reminder scheduling (days before due date)
- Payment confirmation tracking
- Overdue detection and alerts
- Bill calendar view
- Category grouping
- Late fee estimation
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.bills")


class BillFrequency(str, Enum):
    ONE_TIME = "one_time"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class BillStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    SNOOZED = "snoozed"


FREQUENCY_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 90,
    "yearly": 365,
}


class Bill:
    def __init__(self, bill_id: str, name: str, amount: float,
                 due_date: str, frequency: str = "monthly",
                 category: str = "utilities",
                 remind_days_before: int = 3,
                 auto_pay: bool = False,
                 notes: str = ""):
        self.bill_id = bill_id
        self.name = name
        self.amount = amount
        self.due_date = due_date
        self.frequency = frequency
        self.category = category
        self.remind_days_before = remind_days_before
        self.auto_pay = auto_pay
        self.notes = notes
        self.status = "pending"
        self.payment_history = []  # [{date, amount, late: bool}]
        self.snooze_until = None
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "bill_id": self.bill_id,
            "name": self.name,
            "amount": round(self.amount, 2),
            "due_date": self.due_date,
            "frequency": self.frequency,
            "category": self.category,
            "status": self.status,
            "remind_days_before": self.remind_days_before,
            "auto_pay": self.auto_pay,
            "notes": self.notes,
            "snooze_until": self.snooze_until,
            "payment_count": len(self.payment_history),
            "created_at": self.created_at,
        }


class BillReminderService:
    """Manage bills and reminders."""

    def __init__(self):
        self.bills = {}  # bill_id -> Bill
        self.user_bills = defaultdict(list)

    def create_bill(self, user_id: str, name: str, amount: float,
                     due_date: str, frequency: str = "monthly",
                     category: str = "utilities",
                     remind_days_before: int = 3,
                     auto_pay: bool = False,
                     notes: str = "") -> dict:
        """Create a new bill."""
        bill_id = str(uuid4())[:8]
        bill = Bill(
            bill_id=bill_id, name=name, amount=amount,
            due_date=due_date, frequency=frequency,
            category=category, remind_days_before=remind_days_before,
            auto_pay=auto_pay, notes=notes,
        )
        self.bills[bill_id] = bill
        self.user_bills[user_id].append(bill_id)
        return bill.to_dict()

    def mark_paid(self, bill_id: str, amount: float = None,
                   paid_date: str = None) -> dict:
        """Mark a bill as paid."""
        if bill_id not in self.bills:
            return {"error": "Bill not found"}

        bill = self.bills[bill_id]
        payment_date = paid_date or datetime.utcnow().isoformat()[:10]
        payment_amount = amount or bill.amount

        # Check if late
        is_late = payment_date > bill.due_date

        bill.payment_history.append({
            "date": payment_date,
            "amount": round(payment_amount, 2),
            "late": is_late,
        })

        bill.status = "paid"

        # If recurring, create next bill
        if bill.frequency != "one_time":
            next_due = self._next_due_date(bill.due_date, bill.frequency)
            bill.due_date = next_due
            bill.status = "pending"

        return bill.to_dict()

    def snooze(self, bill_id: str, days: int = 7) -> dict:
        """Snooze a bill reminder."""
        if bill_id not in self.bills:
            return {"error": "Not found"}
        bill = self.bills[bill_id]
        bill.snooze_until = (datetime.utcnow() + timedelta(days=days)).isoformat()[:10]
        bill.status = "snoozed"
        return bill.to_dict()

    def cancel(self, bill_id: str) -> dict:
        """Cancel a bill."""
        if bill_id not in self.bills:
            return {"error": "Not found"}
        self.bills[bill_id].status = "cancelled"
        return self.bills[bill_id].to_dict()

    def get_upcoming(self, user_id: str, days: int = 30) -> list[dict]:
        """Get bills due in the next N days."""
        bill_ids = self.user_bills.get(user_id, [])
        now = datetime.utcnow()
        upcoming = []

        for bid in bill_ids:
            bill = self.bills.get(bid)
            if not bill or bill.status in ("paid", "cancelled"):
                continue

            due = datetime.fromisoformat(bill.due_date[:10])
            days_until = (due - now).days

            if -30 <= days_until <= days:  # Include overdue up to 30 days
                upcoming.append({
                    **bill.to_dict(),
                    "days_until_due": days_until,
                    "is_overdue": days_until < 0,
                    "late_fee_estimate": self._estimate_late_fee(bill, days_until),
                })

        return sorted(upcoming, key=lambda x: x["days_until_due"])

    def get_overdue(self, user_id: str) -> list[dict]:
        """Get all overdue bills."""
        bill_ids = self.user_bills.get(user_id, [])
        now = datetime.utcnow()
        overdue = []

        for bid in bill_ids:
            bill = self.bills.get(bid)
            if not bill or bill.status != "pending":
                continue
            due = datetime.fromisoformat(bill.due_date[:10])
            if due < now:
                days_overdue = (now - due).days
                overdue.append({
                    **bill.to_dict(),
                    "days_overdue": days_overdue,
                    "status": "overdue",
                    "late_fee_estimate": self._estimate_late_fee(bill, -days_overdue),
                })

        return sorted(overdue, key=lambda x: x["days_overdue"], reverse=True)

    def get_calendar(self, user_id: str, month: int = None,
                      year: int = None) -> dict:
        """Get bills for a specific month (calendar view)."""
        now = datetime.utcnow()
        m = month or now.month
        y = year or now.year

        bill_ids = self.user_bills.get(user_id, [])
        calendar = defaultdict(list)

        for bid in bill_ids:
            bill = self.bills.get(bid)
            if not bill or bill.status == "cancelled":
                continue

            due = datetime.fromisoformat(bill.due_date[:10])
            if due.month == m and due.year == y:
                calendar[due.day].append(bill.to_dict())

        return {
            "month": m,
            "year": y,
            "calendar": {str(k): v for k, v in sorted(calendar.items())},
            "total_due": round(sum(
                bill.amount for day_bills in calendar.values()
                for bill in [self.bills.get(b.get("bill_id"))
                            for b in day_bills]
                if bill
            ), 2),
        }

    def get_summary(self, user_id: str) -> dict:
        """Get bill payment summary."""
        bill_ids = self.user_bills.get(user_id, [])
        bills = [self.bills[bid] for bid in bill_ids if bid in self.bills]

        total_monthly = sum(
            b.amount * ({"weekly": 4.33, "biweekly": 2.17,
                        "monthly": 1, "quarterly": 0.33,
                        "yearly": 0.083, "one_time": 0}.get(b.frequency, 1))
            for b in bills if b.status not in ("cancelled",)
        )

        by_category = defaultdict(float)
        for b in bills:
            if b.status != "cancelled":
                by_category[b.category] += b.amount

        # Payment stats
        total_paid = sum(len(b.payment_history) for b in bills)
        late_payments = sum(
            sum(1 for p in b.payment_history if p.get("late"))
            for b in bills
        )

        return {
            "total_bills": len(bills),
            "active_bills": len([b for b in bills if b.status not in ("cancelled",)]),
            "total_monthly_estimate": round(total_monthly, 2),
            "by_category": {k: round(v, 2) for k, v in
                           sorted(by_category.items(), key=lambda x: x[1], reverse=True)},
            "payment_history_count": total_paid,
            "late_payment_count": late_payments,
            "late_payment_rate": round(late_payments / max(total_paid, 1) * 100, 1),
        }

    def _next_due_date(self, due_date: str, frequency: str) -> str:
        """Calculate next due date for recurring bills."""
        due = datetime.fromisoformat(due_date[:10])
        days = FREQUENCY_DAYS.get(frequency, 30)
        next_due = due + timedelta(days=days)
        return next_due.isoformat()[:10]

    def _estimate_late_fee(self, bill: Bill, days_until: int) -> float:
        """Estimate late fee (typically 1-5% of bill or $25-50 flat)."""
        if days_until >= 0:
            return 0
        days_late = abs(days_until)
        # Assume 2% of bill amount per month late, capped at 25%
        monthly_fee = bill.amount * 0.02
        months_late = max(days_late / 30, 0.5)
        return round(min(monthly_fee * months_late, bill.amount * 0.25), 2)

    def get_all(self, user_id: str, status: str = None) -> list[dict]:
        """Get all bills."""
        bill_ids = self.user_bills.get(user_id, [])
        bills = [self.bills[bid].to_dict() for bid in bill_ids
                if bid in self.bills]
        if status:
            bills = [b for b in bills if b["status"] == status]
        return bills
