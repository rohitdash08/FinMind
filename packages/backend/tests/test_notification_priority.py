"""
Tests for notification priority & grouping system (#122).
"""

import pytest
import socket
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

def _redis_available():
    try:
        s = socket.create_connection(("localhost", 6379), timeout=0.5)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False

requires_redis = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not available in test environment"
)

from app.services.notification_priority import (
    classify,
    enrich_notification,
    group_and_sort,
    flatten_sorted,
    summary,
    NotificationPriority,
    NotificationGroup,
)


# ─── Unit tests: service layer ───────────────────────────────────────────────

class TestClassify:
    def test_known_category_bill_due_today(self):
        group, priority = classify("bill_due_today")
        assert group == "bills"
        assert priority == NotificationPriority.CRITICAL

    def test_known_category_weekly_summary(self):
        group, priority = classify("weekly_summary")
        assert group == "insights"
        assert priority == NotificationPriority.LOW

    def test_unknown_category_defaults_to_system_normal(self):
        group, priority = classify("some_unknown_type")
        assert group == "system"
        assert priority == NotificationPriority.NORMAL

    def test_security_alert_is_critical(self):
        group, priority = classify("security_alert")
        assert group == "system"
        assert priority == NotificationPriority.CRITICAL

    def test_low_balance_is_critical(self):
        _, priority = classify("low_balance")
        assert priority == NotificationPriority.CRITICAL

    def test_budget_exceeded_is_high(self):
        _, priority = classify("budget_exceeded")
        assert priority == NotificationPriority.HIGH


class TestEnrichNotification:
    def test_adds_group_and_priority(self):
        notif = {"id": "1", "category": "bill_due_today", "message": "Pay up"}
        enriched = enrich_notification(notif)
        assert enriched["group"] == "bills"
        assert enriched["priority"] == int(NotificationPriority.CRITICAL)
        assert enriched["priority_label"] == "critical"

    def test_preserves_original_fields(self):
        notif = {"id": "abc", "category": "tip", "amount": 42, "message": "Save more"}
        enriched = enrich_notification(notif)
        assert enriched["id"] == "abc"
        assert enriched["amount"] == 42

    def test_missing_category_defaults_gracefully(self):
        enriched = enrich_notification({"id": "x"})
        assert enriched["group"] == "system"
        assert enriched["priority"] == int(NotificationPriority.NORMAL)


class TestGroupAndSort:
    def _make(self, categories):
        return [{"id": str(i), "category": c} for i, c in enumerate(categories)]

    def test_groups_by_correct_key(self):
        notifs = self._make(["bill_due_today", "tip", "budget_exceeded"])
        grouped = group_and_sort(notifs)
        assert "bills" in grouped
        assert "insights" in grouped
        assert "alerts" in grouped

    def test_groups_sorted_by_max_priority_desc(self):
        notifs = self._make(["tip", "bill_overdue", "reminder"])
        grouped = group_and_sort(notifs)
        keys = list(grouped.keys())
        # bills has CRITICAL, should be first
        assert keys[0] == "bills"

    def test_within_group_sorted_by_priority_desc(self):
        notifs = [
            {"id": "1", "category": "bill_due_soon"},    # HIGH
            {"id": "2", "category": "bill_due_today"},   # CRITICAL
            {"id": "3", "category": "bill_paid"},        # NORMAL
        ]
        grouped = group_and_sort(notifs)
        bills = grouped["bills"]
        priorities = [n["priority"] for n in bills]
        assert priorities == sorted(priorities, reverse=True)


class TestFlattenSorted:
    def test_sorted_by_priority_desc(self):
        notifs = [
            {"id": "1", "category": "tip", "created_at": "2026-04-03T10:00:00"},
            {"id": "2", "category": "bill_overdue", "created_at": "2026-04-03T09:00:00"},
            {"id": "3", "category": "budget_exceeded", "created_at": "2026-04-03T08:00:00"},
        ]
        flat = flatten_sorted(notifs)
        # bill_overdue (CRITICAL) first, budget_exceeded (HIGH) second, tip (LOW) last
        assert flat[0]["category"] == "bill_overdue"
        assert flat[-1]["category"] == "tip"

    def test_limit_respected(self):
        notifs = [{"id": str(i), "category": "reminder"} for i in range(10)]
        flat = flatten_sorted(notifs, limit=3)
        assert len(flat) == 3

    def test_empty_list(self):
        assert flatten_sorted([]) == []


class TestSummary:
    def test_counts_correctly(self):
        notifs = [
            {"category": "bill_due_today"},
            {"category": "bill_overdue"},
            {"category": "tip"},
            {"category": "reminder"},
        ]
        s = summary(notifs)
        assert s["total"] == 4
        assert s["by_group"]["bills"] == 2
        assert s["by_group"]["insights"] == 1
        assert s["by_group"]["reminders"] == 1
        assert s["critical"] == 2
        assert s["has_critical"] is True

    def test_no_critical(self):
        notifs = [{"category": "tip"}, {"category": "reminder"}]
        s = summary(notifs)
        assert s["has_critical"] is False
        assert s["critical"] == 0


# ─── API endpoint tests ──────────────────────────────────────────────────────


@requires_redis
class TestNotificationEndpoints:
    def test_list_requires_auth(self, client, auth_header):
        r = client.get("/notifications")
        assert r.status_code == 401

    def test_summary_requires_auth(self, client):
        r = client.get("/notifications/summary")
        assert r.status_code == 401

    def test_classify_requires_auth(self, client):
        r = client.post("/notifications/classify", json={"category": "tip"})
        assert r.status_code == 401

    def test_list_returns_grouped_view(self, client, auth_header):
        r = client.get("/notifications", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "view" in data
        assert data["view"] == "grouped"
        assert "groups" in data
        assert "total" in data

    def test_list_flat_view(self, client, auth_header):
        r = client.get("/notifications?view=flat", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["view"] == "flat"
        assert "notifications" in data

    def test_list_flat_with_limit(self, client, auth_header):
        r = client.get("/notifications?view=flat&limit=2", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["notifications"]) <= 2

    def test_invalid_priority_filter(self, client, auth_header):
        r = client.get("/notifications?priority=superurgent", headers=auth_header)
        assert r.status_code == 400

    def test_summary_endpoint(self, client, auth_header):
        r = client.get("/notifications/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "total" in data
        assert "has_critical" in data
        assert "by_group" in data
        assert "by_priority" in data

    def test_classify_single(self, client, auth_header):
        r = client.post("/notifications/classify",
                        json={"category": "bill_due_today"},
                        headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["group"] == "bills"
        assert data["priority_label"] == "critical"

    def test_classify_batch(self, client, auth_header):
        r = client.post("/notifications/classify",
                        json={"notifications": [
                            {"id": "1", "category": "tip"},
                            {"id": "2", "category": "bill_overdue"},
                        ]},
                        headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["classified"]) == 2

    def test_categories_endpoint(self, client, auth_header):
        r = client.get("/notifications/categories", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "categories" in data
        assert data["total"] > 0