"""Tests for notification priority & grouping system."""

import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import Notification


# ═══════════════════════════════════════════════════════════════════
# Service unit tests
# ═══════════════════════════════════════════════════════════════════


class TestCreateNotification:
    """Test notification creation."""

    def test_create_basic(self, client, auth_header):
        from app.services.notification_priority import create_notification

        with client.application.app_context():
            result = create_notification(1, "Test", "Hello world")

        assert result["title"] == "Test"
        assert result["message"] == "Hello world"
        assert result["priority"] == "normal"
        assert result["category"] == "general"
        assert result["is_read"] is False

    def test_create_with_priority(self, client, auth_header):
        from app.services.notification_priority import create_notification

        with client.application.app_context():
            result = create_notification(1, "Alert", "Critical!", priority="critical")

        assert result["priority"] == "critical"

    def test_invalid_priority_defaults(self, client, auth_header):
        from app.services.notification_priority import create_notification

        with client.application.app_context():
            result = create_notification(1, "Test", "msg", priority="invalid")

        assert result["priority"] == "normal"

    def test_invalid_category_defaults(self, client, auth_header):
        from app.services.notification_priority import create_notification

        with client.application.app_context():
            result = create_notification(1, "Test", "msg", category="unknown")

        assert result["category"] == "general"

    def test_create_with_group_key(self, client, auth_header):
        from app.services.notification_priority import create_notification

        with client.application.app_context():
            result = create_notification(
                1, "Bill Due", "Pay rent", group_key="bills_march"
            )

        assert result["group_key"] == "bills_march"

    def test_create_with_action(self, client, auth_header):
        from app.services.notification_priority import create_notification

        with client.application.app_context():
            result = create_notification(
                1, "Test", "msg",
                action_url="/bills/42",
                action_type="navigate",
            )

        assert result["action_url"] == "/bills/42"
        assert result["action_type"] == "navigate"


class TestGetNotifications:
    """Test notification listing with priority sorting."""

    def _seed(self, client):
        from app.services.notification_priority import create_notification

        with client.application.app_context():
            create_notification(1, "Low", "low msg", priority="low")
            create_notification(1, "Critical", "urgent!", priority="critical")
            create_notification(1, "Normal", "normal msg", priority="normal")
            create_notification(1, "High", "important", priority="high")

    def test_priority_ordering(self, client, auth_header):
        from app.services.notification_priority import get_notifications

        self._seed(client)
        with client.application.app_context():
            result = get_notifications(1)

        titles = [n["title"] for n in result["notifications"]]
        assert titles[0] == "Critical"
        assert titles[1] == "High"
        assert titles[2] == "Normal"
        assert titles[3] == "Low"

    def test_filter_by_priority(self, client, auth_header):
        from app.services.notification_priority import get_notifications

        self._seed(client)
        with client.application.app_context():
            result = get_notifications(1, priority="critical")

        assert result["total"] == 1
        assert result["notifications"][0]["priority"] == "critical"

    def test_filter_by_read_status(self, client, auth_header):
        from app.services.notification_priority import get_notifications, mark_read

        self._seed(client)
        with client.application.app_context():
            notifs = get_notifications(1)
            mark_read(notifs["notifications"][0]["id"], 1)
            unread = get_notifications(1, is_read=False)

        assert unread["total"] == 3

    def test_pagination(self, client, auth_header):
        from app.services.notification_priority import get_notifications

        self._seed(client)
        with client.application.app_context():
            result = get_notifications(1, limit=2, offset=0)

        assert len(result["notifications"]) == 2
        assert result["total"] == 4

    def test_empty_list(self, client, auth_header):
        from app.services.notification_priority import get_notifications

        with client.application.app_context():
            result = get_notifications(1)

        assert result["notifications"] == []
        assert result["total"] == 0


class TestGroupedNotifications:
    """Test notification grouping."""

    def test_grouped(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, get_grouped_notifications,
        )

        with client.application.app_context():
            create_notification(1, "Bill 1", "msg", group_key="bills")
            create_notification(1, "Bill 2", "msg", group_key="bills")
            create_notification(1, "Solo", "msg")  # ungrouped
            result = get_grouped_notifications(1)

        assert result["total_groups"] == 1
        assert result["groups"][0]["count"] == 2
        assert result["total_ungrouped"] == 1

    def test_grouped_unread_count(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, get_grouped_notifications, mark_read,
        )

        with client.application.app_context():
            n1 = create_notification(1, "A", "msg", group_key="g1")
            create_notification(1, "B", "msg", group_key="g1")
            mark_read(n1["id"], 1)
            result = get_grouped_notifications(1)

        assert result["groups"][0]["unread_count"] == 1

    def test_filter_by_category(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, get_grouped_notifications,
        )

        with client.application.app_context():
            create_notification(1, "A", "msg", group_key="g", category="bill_due")
            create_notification(1, "B", "msg", group_key="g", category="security")
            result = get_grouped_notifications(1, category="bill_due")

        assert result["total_groups"] == 1
        assert result["groups"][0]["count"] == 1


class TestMarkRead:
    """Test read/dismiss operations."""

    def test_mark_read(self, client, auth_header):
        from app.services.notification_priority import create_notification, mark_read

        with client.application.app_context():
            n = create_notification(1, "Test", "msg")
            result = mark_read(n["id"], 1)

        assert result["is_read"] is True

    def test_mark_read_nonexistent(self, client, auth_header):
        from app.services.notification_priority import mark_read

        with client.application.app_context():
            assert mark_read(9999, 1) is None

    def test_mark_all_read(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, mark_all_read, get_unread_count,
        )

        with client.application.app_context():
            create_notification(1, "A", "msg")
            create_notification(1, "B", "msg")
            result = mark_all_read(1)
            count = get_unread_count(1)

        assert result["marked_read"] == 2
        assert count["total"] == 0

    def test_dismiss(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, dismiss_notification, get_notifications,
        )

        with client.application.app_context():
            n = create_notification(1, "Test", "msg")
            dismiss_notification(n["id"], 1)
            result = get_notifications(1)

        assert result["total"] == 0

    def test_dismiss_group(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, dismiss_group, get_notifications,
        )

        with client.application.app_context():
            create_notification(1, "A", "msg", group_key="g1")
            create_notification(1, "B", "msg", group_key="g1")
            create_notification(1, "C", "msg")  # ungrouped
            dismiss_group(1, "g1")
            result = get_notifications(1)

        assert result["total"] == 1  # only ungrouped remains


class TestUnreadCount:
    """Test unread count."""

    def test_counts(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, get_unread_count,
        )

        with client.application.app_context():
            create_notification(1, "A", "msg", priority="critical", category="security")
            create_notification(1, "B", "msg", priority="low", category="general")
            result = get_unread_count(1)

        assert result["total"] == 2
        assert result["by_priority"]["critical"] == 1
        assert result["by_priority"]["low"] == 1
        assert result["by_category"]["security"] == 1


class TestNotificationStats:
    """Test statistics."""

    def test_empty_stats(self, client, auth_header):
        from app.services.notification_priority import get_notification_stats

        with client.application.app_context():
            stats = get_notification_stats(1)

        assert stats["total"] == 0
        assert stats["read_rate"] == 0.0

    def test_stats_with_data(self, client, auth_header):
        from app.services.notification_priority import (
            create_notification, mark_read, get_notification_stats,
        )

        with client.application.app_context():
            n1 = create_notification(1, "A", "msg", priority="high")
            create_notification(1, "B", "msg", priority="low")
            mark_read(n1["id"], 1)
            stats = get_notification_stats(1)

        assert stats["total"] == 2
        assert stats["read"] == 1
        assert stats["read_rate"] == 0.5
        assert stats["by_priority"]["high"] == 1


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestNotificationRoutes:
    """Integration tests for /notifications/* endpoints."""

    # ── POST /notifications/send ──
    def test_send(self, client, auth_header):
        r = client.post("/notifications/send",
                        json={"title": "Test", "message": "Hello"},
                        headers=auth_header)
        assert r.status_code == 201
        assert r.get_json()["title"] == "Test"

    def test_send_with_priority(self, client, auth_header):
        r = client.post("/notifications/send",
                        json={"title": "Alert", "message": "!",
                              "priority": "critical", "category": "security"},
                        headers=auth_header)
        assert r.status_code == 201
        assert r.get_json()["priority"] == "critical"

    def test_send_missing_fields(self, client, auth_header):
        r = client.post("/notifications/send", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_send_unauthorized(self, client):
        r = client.post("/notifications/send",
                        json={"title": "T", "message": "M"})
        assert r.status_code == 401

    # ── GET /notifications ──
    def test_list(self, client, auth_header):
        client.post("/notifications/send",
                    json={"title": "T", "message": "M"},
                    headers=auth_header)
        r = client.get("/notifications", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] >= 1

    def test_list_with_filters(self, client, auth_header):
        r = client.get("/notifications?priority=high&is_read=false&limit=10",
                       headers=auth_header)
        assert r.status_code == 200

    # ── GET /notifications/grouped ──
    def test_grouped(self, client, auth_header):
        client.post("/notifications/send",
                    json={"title": "A", "message": "M", "group_key": "g1"},
                    headers=auth_header)
        client.post("/notifications/send",
                    json={"title": "B", "message": "M", "group_key": "g1"},
                    headers=auth_header)
        r = client.get("/notifications/grouped", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total_groups"] >= 1

    # ── POST /notifications/<id>/read ──
    def test_mark_read_route(self, client, auth_header):
        cr = client.post("/notifications/send",
                         json={"title": "T", "message": "M"},
                         headers=auth_header)
        nid = cr.get_json()["id"]
        r = client.post(f"/notifications/{nid}/read", json={},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["is_read"] is True

    def test_mark_read_nonexistent(self, client, auth_header):
        r = client.post("/notifications/9999/read", json={},
                        headers=auth_header)
        assert r.status_code == 404

    # ── POST /notifications/read-all ──
    def test_read_all_route(self, client, auth_header):
        client.post("/notifications/send",
                    json={"title": "T", "message": "M"},
                    headers=auth_header)
        r = client.post("/notifications/read-all", json={},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["marked_read"] >= 1

    # ── POST /notifications/<id>/dismiss ──
    def test_dismiss_route(self, client, auth_header):
        cr = client.post("/notifications/send",
                         json={"title": "T", "message": "M"},
                         headers=auth_header)
        nid = cr.get_json()["id"]
        r = client.post(f"/notifications/{nid}/dismiss", json={},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["is_dismissed"] is True

    # ── POST /notifications/dismiss-group ──
    def test_dismiss_group_route(self, client, auth_header):
        client.post("/notifications/send",
                    json={"title": "T", "message": "M", "group_key": "gx"},
                    headers=auth_header)
        r = client.post("/notifications/dismiss-group",
                        json={"group_key": "gx"},
                        headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["dismissed"] >= 1

    def test_dismiss_group_missing_key(self, client, auth_header):
        r = client.post("/notifications/dismiss-group", json={},
                        headers=auth_header)
        assert r.status_code == 400

    # ── GET /notifications/unread ──
    def test_unread_route(self, client, auth_header):
        client.post("/notifications/send",
                    json={"title": "T", "message": "M"},
                    headers=auth_header)
        r = client.get("/notifications/unread", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] >= 1

    # ── GET /notifications/stats ──
    def test_stats_route(self, client, auth_header):
        r = client.get("/notifications/stats", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "read_rate" in body
        assert "by_priority" in body

    def test_stats_with_days(self, client, auth_header):
        r = client.get("/notifications/stats?days=7", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["period_days"] == 7
