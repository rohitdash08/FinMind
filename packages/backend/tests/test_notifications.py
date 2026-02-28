"""Tests for notification priority and grouping system."""

import pytest
from app.services.notifications import (
    NotificationManager, Priority, NotificationGroup,
    PRIORITY_RULES, GROUP_RULES,
)


class TestPriorityRules:
    def test_critical_events(self):
        assert PRIORITY_RULES["bill_overdue"] == Priority.CRITICAL
        assert PRIORITY_RULES["payment_failed"] == Priority.CRITICAL
        assert PRIORITY_RULES["security_alert"] == Priority.CRITICAL

    def test_high_events(self):
        assert PRIORITY_RULES["bill_due_today"] == Priority.HIGH
        assert PRIORITY_RULES["large_expense"] == Priority.HIGH

    def test_group_mapping(self):
        assert GROUP_RULES["bill_overdue"] == NotificationGroup.BILLS
        assert GROUP_RULES["large_expense"] == NotificationGroup.EXPENSES
        assert GROUP_RULES["budget_exceeded"] == NotificationGroup.BUDGET


class TestNotificationManager:
    def test_notify(self):
        m = NotificationManager()
        n = m.notify("bill_overdue", "Bill Overdue", "Electric bill", user_id=1)
        assert n.priority == Priority.CRITICAL
        assert n.group == NotificationGroup.BILLS

    def test_get_sorted_by_priority(self):
        m = NotificationManager()
        m.notify("tip", "Tip", "Save more", user_id=1)
        m.notify("bill_overdue", "Overdue", "Pay now", user_id=1)
        m.notify("budget_warning", "Warning", "80% used", user_id=1)
        notes = m.get_notifications(1)
        assert notes[0]["priority"] == "critical"
        assert notes[1]["priority"] == "medium"
        assert notes[2]["priority"] == "info"

    def test_filter_unread(self):
        m = NotificationManager()
        n = m.notify("tip", "Tip", "msg", user_id=1)
        m.notify("tip", "Tip2", "msg2", user_id=1)
        m.mark_read(1, n.id)
        unread = m.get_notifications(1, unread_only=True)
        assert len(unread) == 1

    def test_filter_group(self):
        m = NotificationManager()
        m.notify("bill_overdue", "Bill", "msg", user_id=1)
        m.notify("large_expense", "Expense", "msg", user_id=1)
        bills = m.get_notifications(1, group="bills")
        assert len(bills) == 1
        assert bills[0]["group"] == "bills"

    def test_filter_priority(self):
        m = NotificationManager()
        m.notify("bill_overdue", "Critical", "msg", user_id=1)
        m.notify("tip", "Info", "msg", user_id=1)
        critical = m.get_notifications(1, priority="critical")
        assert len(critical) == 1

    def test_grouped(self):
        m = NotificationManager()
        m.notify("bill_overdue", "B1", "m", user_id=1)
        m.notify("bill_due_today", "B2", "m", user_id=1)
        m.notify("large_expense", "E1", "m", user_id=1)
        grouped = m.get_grouped(1)
        assert "bills" in grouped
        assert grouped["bills"]["count"] == 2
        assert "expenses" in grouped

    def test_group_collapse(self):
        m = NotificationManager()
        for i in range(8):
            m.notify("bill_due_week", f"Bill {i}", "msg", user_id=1)
        grouped = m.get_grouped(1)
        assert grouped["bills"]["collapsed"] is True
        assert len(grouped["bills"]["items"]) == 5

    def test_mark_read(self):
        m = NotificationManager()
        n = m.notify("tip", "Tip", "msg", user_id=1)
        assert m.mark_read(1, n.id) is True
        assert m.mark_read(1, "fake") is False

    def test_mark_all_read(self):
        m = NotificationManager()
        m.notify("tip", "T1", "m", user_id=1)
        m.notify("tip", "T2", "m", user_id=1)
        count = m.mark_all_read(1)
        assert count == 2

    def test_mark_all_read_by_group(self):
        m = NotificationManager()
        m.notify("bill_overdue", "B", "m", user_id=1)
        m.notify("tip", "T", "m", user_id=1)
        count = m.mark_all_read(1, group="bills")
        assert count == 1

    def test_dismiss(self):
        m = NotificationManager()
        n = m.notify("tip", "Tip", "msg", user_id=1)
        assert m.dismiss(1, n.id) is True
        assert m.dismiss(1, "fake") is False

    def test_summary(self):
        m = NotificationManager()
        m.notify("bill_overdue", "B", "m", user_id=1)
        m.notify("tip", "T", "m", user_id=1)
        s = m.get_summary(1)
        assert s["unread_total"] == 2
        assert s["by_priority"]["critical"] == 1

    def test_preferences(self):
        m = NotificationManager()
        m.set_preferences(1, {"critical": True, "info": False})
        p = m.get_preferences(1)
        assert p["critical"] is True
        assert p["info"] is False

    def test_default_preferences(self):
        m = NotificationManager()
        p = m.get_preferences(999)
        assert p["critical"] is True
        assert p["info"] is False

    def test_user_isolation(self):
        m = NotificationManager()
        m.notify("tip", "T", "m", user_id=1)
        m.notify("tip", "T", "m", user_id=2)
        assert len(m.get_notifications(1)) == 1
        assert len(m.get_notifications(2)) == 1


class TestNotificationAPI:
    def test_list(self, client):
        resp = client.get("/notifications/?user_id=1")
        assert resp.status_code == 200

    def test_create(self, client):
        resp = client.post("/notifications/", json={
            "event_type": "bill_overdue",
            "title": "Bill Overdue",
            "message": "Electric bill is overdue",
            "user_id": 1,
        })
        assert resp.status_code == 201
        assert resp.get_json()["priority"] == "critical"

    def test_create_missing_field(self, client):
        resp = client.post("/notifications/", json={"title": "x"})
        assert resp.status_code == 400

    def test_summary(self, client):
        resp = client.get("/notifications/summary?user_id=1")
        assert resp.status_code == 200

    def test_grouped(self, client):
        resp = client.get("/notifications/grouped?user_id=1")
        assert resp.status_code == 200

    def test_mark_all_read(self, client):
        resp = client.post("/notifications/read-all?user_id=1")
        assert resp.status_code == 200
