"""Tests for Bill Reminder."""

import pytest
from datetime import datetime, timedelta


class TestBillReminder:
    def test_create_bill(self):
        from app.services.bill_reminder import BillReminderService
        svc = BillReminderService()
        due = (datetime.utcnow() + timedelta(days=15)).isoformat()[:10]
        bill = svc.create_bill("user1", "Electric", 120.50, due, "monthly", "utilities")
        assert bill["name"] == "Electric"
        assert bill["amount"] == 120.50

    def test_mark_paid(self):
        from app.services.bill_reminder import BillReminderService
        svc = BillReminderService()
        due = (datetime.utcnow() + timedelta(days=15)).isoformat()[:10]
        bill = svc.create_bill("user1", "Internet", 79.99, due)
        result = svc.mark_paid(bill["bill_id"])
        assert result["status"] == "pending"  # Recurring, next one pending

    def test_overdue(self):
        from app.services.bill_reminder import BillReminderService
        svc = BillReminderService()
        past_due = (datetime.utcnow() - timedelta(days=5)).isoformat()[:10]
        svc.create_bill("user1", "Rent", 2000, past_due)
        overdue = svc.get_overdue("user1")
        assert len(overdue) == 1
        assert overdue[0]["days_overdue"] > 0

    def test_calendar(self):
        from app.services.bill_reminder import BillReminderService
        svc = BillReminderService()
        now = datetime.utcnow()
        due = now.isoformat()[:10]
        svc.create_bill("user1", "Phone", 85, due)
        cal = svc.get_calendar("user1", now.month, now.year)
        assert cal["total_due"] > 0

    def test_late_fee_estimate(self):
        from app.services.bill_reminder import BillReminderService
        svc = BillReminderService()
        past_due = (datetime.utcnow() - timedelta(days=35)).isoformat()[:10]
        svc.create_bill("user1", "Credit Card", 500, past_due)
        upcoming = svc.get_upcoming("user1", 60)
        assert any(b["late_fee_estimate"] > 0 for b in upcoming)

    def test_summary(self):
        from app.services.bill_reminder import BillReminderService
        svc = BillReminderService()
        due = (datetime.utcnow() + timedelta(days=10)).isoformat()[:10]
        svc.create_bill("user1", "Netflix", 15.99, due, "monthly", "entertainment")
        svc.create_bill("user1", "Rent", 1500, due, "monthly", "housing")
        summary = svc.get_summary("user1")
        assert summary["total_bills"] == 2
        assert summary["total_monthly_estimate"] > 0
