"""Tests for smart reminder timing optimization."""

import pytest
from app.models import UserActivityLog, ReminderPreference
from app.extensions import db
from app.services.smart_reminder import (
    log_activity,
    get_activity_pattern,
    get_preferences,
    update_preferences,
    get_optimal_time,
    get_optimal_days,
    should_send_reminder,
    _is_quiet_hour,
)


# ── Helper ────────────────────────────────────────────────────────


def _seed_activities(user_id, hour, day, count=1):
    """Create activity log entries for testing."""
    for _ in range(count):
        entry = UserActivityLog(
            user_id=user_id,
            action="app_open",
            hour_of_day=hour,
            day_of_week=day,
        )
        db.session.add(entry)
    db.session.commit()


# ── Unit: _is_quiet_hour ──────────────────────────────────────────


class TestIsQuietHour:
    def test_normal_range(self):
        # 22-7 wraps around midnight
        assert _is_quiet_hour(23, 22, 7) is True
        assert _is_quiet_hour(3, 22, 7) is True
        assert _is_quiet_hour(10, 22, 7) is False

    def test_same_day_range(self):
        # 1-5 doesn't wrap
        assert _is_quiet_hour(3, 1, 5) is True
        assert _is_quiet_hour(0, 1, 5) is False
        assert _is_quiet_hour(5, 1, 5) is False

    def test_boundary(self):
        assert _is_quiet_hour(22, 22, 7) is True  # start is inclusive
        assert _is_quiet_hour(7, 22, 7) is False   # end is exclusive


# ── Service: log_activity ─────────────────────────────────────────


class TestLogActivity:
    def test_log_creates_entry(self, app_fixture):
        with app_fixture.app_context():
            result = log_activity(1, "app_open")
            assert result["action"] == "app_open"
            assert "hour_of_day" in result
            assert "day_of_week" in result
            assert "id" in result

    def test_log_persists(self, app_fixture):
        with app_fixture.app_context():
            log_activity(1, "expense_added")
            logs = UserActivityLog.query.filter_by(user_id=1).all()
            assert len(logs) == 1
            assert logs[0].action == "expense_added"


# ── Service: get_activity_pattern ─────────────────────────────────


class TestGetActivityPattern:
    def test_empty_pattern(self, app_fixture):
        with app_fixture.app_context():
            result = get_activity_pattern(1)
            assert result["total_activities"] == 0
            assert result["peak_hours"] == []
            assert result["most_active_hour"] is None

    def test_pattern_with_data(self, app_fixture):
        with app_fixture.app_context():
            _seed_activities(1, hour=10, day=1, count=5)
            _seed_activities(1, hour=14, day=3, count=3)

            result = get_activity_pattern(1)
            assert result["total_activities"] == 8
            assert result["most_active_hour"] == 10
            assert 10 in result["peak_hours"]

    def test_hourly_distribution(self, app_fixture):
        with app_fixture.app_context():
            _seed_activities(1, hour=9, day=0, count=4)
            result = get_activity_pattern(1)
            assert int(result["hourly_distribution"]["9"]) == 4
            assert int(result["hourly_distribution"]["10"]) == 0

    def test_daily_distribution(self, app_fixture):
        with app_fixture.app_context():
            _seed_activities(1, hour=9, day=2, count=3)
            result = get_activity_pattern(1)
            assert int(result["daily_distribution"]["2"]) == 3
            assert result["most_active_day"] == 2


# ── Service: preferences ──────────────────────────────────────────


class TestPreferences:
    def test_default_preferences(self, app_fixture):
        with app_fixture.app_context():
            result = get_preferences(1)
            assert result["preferred_hour"] == 9
            assert result["auto_optimize"] is True
            assert result["quiet_hours_start"] == 22

    def test_update_creates_preferences(self, app_fixture):
        with app_fixture.app_context():
            result = update_preferences(1, preferred_hour=14, auto_optimize=False)
            assert result["preferred_hour"] == 14
            assert result["auto_optimize"] is False

    def test_update_existing_preferences(self, app_fixture):
        with app_fixture.app_context():
            update_preferences(1, preferred_hour=10)
            result = update_preferences(1, preferred_hour=15)
            assert result["preferred_hour"] == 15

    def test_partial_update(self, app_fixture):
        with app_fixture.app_context():
            update_preferences(1, preferred_hour=10, quiet_hours_start=23)
            result = update_preferences(1, quiet_hours_start=21)
            assert result["preferred_hour"] == 10  # unchanged
            assert result["quiet_hours_start"] == 21  # updated


# ── Service: get_optimal_time ─────────────────────────────────────


class TestGetOptimalTime:
    def test_insufficient_data(self, app_fixture):
        with app_fixture.app_context():
            result = get_optimal_time(1)
            assert result["method"] == "default_insufficient_data"
            assert result["confidence"] == 0.3
            assert result["optimal_hour"] == 9

    def test_user_preference_method(self, app_fixture):
        with app_fixture.app_context():
            update_preferences(1, auto_optimize=False, preferred_hour=14)
            result = get_optimal_time(1)
            assert result["method"] == "user_preference"
            assert result["optimal_hour"] == 14
            assert result["confidence"] == 1.0

    def test_activity_analysis(self, app_fixture):
        with app_fixture.app_context():
            # Seed enough data for analysis (>= 5 activities)
            _seed_activities(1, hour=10, day=1, count=6)
            _seed_activities(1, hour=14, day=2, count=2)
            result = get_optimal_time(1)
            assert result["method"] == "activity_analysis"
            assert result["optimal_hour"] == 10  # most active
            assert result["confidence"] > 0.3

    def test_quiet_hours_filtered(self, app_fixture):
        with app_fixture.app_context():
            update_preferences(1, quiet_hours_start=22, quiet_hours_end=7)
            # Seed activities during quiet hours
            _seed_activities(1, hour=23, day=1, count=10)
            # Seed some outside quiet hours
            _seed_activities(1, hour=10, day=1, count=3)
            result = get_optimal_time(1)
            assert result["optimal_hour"] != 23  # quiet hour filtered

    def test_alternatives_provided(self, app_fixture):
        with app_fixture.app_context():
            _seed_activities(1, hour=10, day=1, count=5)
            _seed_activities(1, hour=14, day=2, count=3)
            _seed_activities(1, hour=16, day=3, count=2)
            result = get_optimal_time(1)
            assert isinstance(result["alternative_hours"], list)


# ── Service: get_optimal_days ─────────────────────────────────────


class TestGetOptimalDays:
    def test_insufficient_data_default(self, app_fixture):
        with app_fixture.app_context():
            result = get_optimal_days(1)
            assert result["method"] == "default"
            assert result["confidence"] == 0.3

    def test_activity_based_days(self, app_fixture):
        with app_fixture.app_context():
            _seed_activities(1, hour=10, day=1, count=5)
            _seed_activities(1, hour=10, day=3, count=4)
            _seed_activities(1, hour=10, day=5, count=1)
            result = get_optimal_days(1)
            assert result["method"] == "activity_analysis"
            assert 1 in result["optimal_days"]

    def test_day_scores(self, app_fixture):
        with app_fixture.app_context():
            _seed_activities(1, hour=10, day=0, count=10)
            result = get_optimal_days(1)
            assert float(result["day_scores"]["0"]) == 1.0


# ── Service: should_send_reminder ─────────────────────────────────


class TestShouldSendReminder:
    def test_quiet_hours_block(self, app_fixture):
        with app_fixture.app_context():
            update_preferences(1, quiet_hours_start=22, quiet_hours_end=7)
            result = should_send_reminder(1, current_hour=23)
            assert result["should_send"] is False
            assert result["reason"] == "quiet_hours"

    def test_optimal_window(self, app_fixture):
        with app_fixture.app_context():
            # Default optimal hour is 9 (insufficient data)
            result = should_send_reminder(1, current_hour=9)
            assert result["should_send"] is True
            assert result["reason"] == "optimal_window"

    def test_outside_optimal_window(self, app_fixture):
        with app_fixture.app_context():
            result = should_send_reminder(1, current_hour=15)
            assert result["should_send"] is False
            assert result["reason"] == "outside_optimal_window"

    def test_adjacent_hour_allowed(self, app_fixture):
        with app_fixture.app_context():
            # Default optimal is 9, so 8 and 10 are within ±1
            result = should_send_reminder(1, current_hour=10)
            assert result["should_send"] is True


# ── Routes ────────────────────────────────────────────────────────


class TestSmartReminderRoutes:
    def test_log_activity(self, client, auth_header):
        r = client.post("/smart-reminders/activity",
                        json={"action": "app_open"},
                        headers=auth_header)
        assert r.status_code == 201
        data = r.get_json()
        assert data["action"] == "app_open"

    def test_log_activity_missing_action(self, client, auth_header):
        r = client.post("/smart-reminders/activity",
                        json={},
                        headers=auth_header)
        assert r.status_code == 400

    def test_get_pattern(self, client, auth_header):
        r = client.get("/smart-reminders/activity/pattern",
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "hourly_distribution" in data

    def test_get_preferences(self, client, auth_header):
        r = client.get("/smart-reminders/preferences",
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "preferred_hour" in data

    def test_update_preferences(self, client, auth_header):
        r = client.put("/smart-reminders/preferences",
                       json={"preferred_hour": 14, "auto_optimize": False},
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["preferred_hour"] == 14

    def test_update_preferences_no_data(self, client, auth_header):
        r = client.put("/smart-reminders/preferences",
                       headers=auth_header,
                       content_type="application/json")
        assert r.status_code == 400

    def test_get_optimal_time(self, client, auth_header):
        r = client.get("/smart-reminders/optimal-time",
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "optimal_hour" in data
        assert "confidence" in data
        assert "method" in data

    def test_get_optimal_days(self, client, auth_header):
        r = client.get("/smart-reminders/optimal-days",
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "optimal_days" in data

    def test_should_send(self, client, auth_header):
        r = client.get("/smart-reminders/should-send?hour=10",
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "should_send" in data

    def test_should_send_no_hour(self, client, auth_header):
        r = client.get("/smart-reminders/should-send",
                       headers=auth_header)
        assert r.status_code == 200

    def test_unauthorized(self, client):
        r = client.get("/smart-reminders/optimal-time")
        assert r.status_code == 401
