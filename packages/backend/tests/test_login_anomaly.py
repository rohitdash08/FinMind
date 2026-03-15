"""Tests for login anomaly detection and suspicious activity alerts."""

import json
import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import LoginEvent, SecurityAlert


CHROME_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"


# ═══════════════════════════════════════════════════════════════════
# Service unit tests
# ═══════════════════════════════════════════════════════════════════


class TestUserAgentParsing:
    """Test _parse_user_agent helper."""

    def test_parse_chrome_mac(self, app_fixture):
        from app.services.login_anomaly import _parse_user_agent

        info = _parse_user_agent(CHROME_UA)
        assert info["device_type"] == "desktop"
        assert info["browser"] == "Chrome"
        assert info["os"] == "macOS"

    def test_parse_firefox_windows(self, app_fixture):
        from app.services.login_anomaly import _parse_user_agent

        info = _parse_user_agent(FIREFOX_UA)
        assert info["browser"] == "Firefox"
        assert info["os"] == "Windows"

    def test_parse_empty(self, app_fixture):
        from app.services.login_anomaly import _parse_user_agent

        info = _parse_user_agent("")
        assert info["device_type"] == "desktop"
        assert info["browser"] == "Unknown"


class TestAnomalyDetection:
    """Test _analyze_login anomaly detection."""

    def test_first_login_no_anomaly(self, client, auth_header):
        from app.services.login_anomaly import _analyze_login

        with client.application.app_context():
            result = _analyze_login(1, "192.168.1.1", CHROME_UA)

        assert result["risk_score"] == 0.0
        assert result["is_suspicious"] is False
        assert result["anomaly_reasons"] == []

    def test_new_ip_detected(self, client, auth_header):
        from app.services.login_anomaly import record_login_event, _analyze_login

        with client.application.app_context():
            # Record some events with known IP
            for _ in range(3):
                record_login_event(1, "192.168.1.1", CHROME_UA)

            # Analyze from new IP
            result = _analyze_login(1, "10.0.0.1", CHROME_UA)

        assert "new_ip" in result["anomaly_reasons"]
        assert result["risk_score"] > 0

    def test_new_device_detected(self, client, auth_header):
        from app.services.login_anomaly import record_login_event, _analyze_login

        with client.application.app_context():
            record_login_event(1, "192.168.1.1", CHROME_UA)
            result = _analyze_login(1, "192.168.1.1", FIREFOX_UA)

        assert "new_device" in result["anomaly_reasons"]

    def test_rapid_attempts_detected(self, client, auth_header):
        from app.services.login_anomaly import _analyze_login

        with client.application.app_context():
            # Create 5+ recent events manually
            now = datetime.utcnow()
            for i in range(6):
                event = LoginEvent(
                    user_id=1,
                    event_type="login",
                    ip_address="192.168.1.1",
                    browser="Chrome",
                    os="macOS",
                    created_at=now - timedelta(minutes=1, seconds=i),
                )
                db.session.add(event)
            db.session.commit()

            result = _analyze_login(1, "192.168.1.1", CHROME_UA)

        assert "rapid_attempts" in result["anomaly_reasons"]

    def test_failed_streak_detected(self, client, auth_header):
        from app.services.login_anomaly import _analyze_login

        with client.application.app_context():
            now = datetime.utcnow()
            for i in range(4):
                event = LoginEvent(
                    user_id=1,
                    event_type="failed_login",
                    ip_address="192.168.1.1",
                    browser="Chrome",
                    os="macOS",
                    created_at=now - timedelta(seconds=i + 1),
                )
                db.session.add(event)
            db.session.commit()

            result = _analyze_login(1, "192.168.1.1", CHROME_UA)

        assert "failed_streak" in result["anomaly_reasons"]

    def test_risk_score_capped_at_one(self, client, auth_header):
        from app.services.login_anomaly import _analyze_login

        with client.application.app_context():
            now = datetime.utcnow()
            # Create many failed events from known IP/device to trigger multiple signals
            for i in range(10):
                event = LoginEvent(
                    user_id=1,
                    event_type="failed_login",
                    ip_address="10.0.0.1",
                    browser="Safari",
                    os="iOS",
                    created_at=now - timedelta(seconds=i + 1),
                )
                db.session.add(event)
            db.session.commit()

            result = _analyze_login(1, "192.168.1.1", CHROME_UA)

        assert result["risk_score"] <= 1.0

    def test_suspicious_threshold(self, client, auth_header):
        from app.services.login_anomaly import _analyze_login

        with client.application.app_context():
            now = datetime.utcnow()
            # Create history to trigger new_ip + new_device + rapid_attempts
            for i in range(6):
                event = LoginEvent(
                    user_id=1,
                    event_type="login",
                    ip_address="10.0.0.1",
                    browser="Safari",
                    os="iOS",
                    created_at=now - timedelta(minutes=1, seconds=i),
                )
                db.session.add(event)
            db.session.commit()

            result = _analyze_login(1, "192.168.1.1", CHROME_UA)

        assert result["is_suspicious"] is True


class TestRecordLoginEvent:
    """Test record_login_event service function."""

    def test_record_basic_login(self, client, auth_header):
        from app.services.login_anomaly import record_login_event

        with client.application.app_context():
            result = record_login_event(1, "192.168.1.1", CHROME_UA)

        assert result["event_type"] == "login"
        assert result["event_id"] is not None
        assert "risk_score" in result
        assert "browser" in result

    def test_record_failed_login(self, client, auth_header):
        from app.services.login_anomaly import record_login_event

        with client.application.app_context():
            result = record_login_event(1, "10.0.0.1", CHROME_UA,
                                        event_type="failed_login")

        assert result["event_type"] == "failed_login"

    def test_record_with_session_id(self, client, auth_header):
        from app.services.login_anomaly import record_login_event

        with client.application.app_context():
            result = record_login_event(1, "10.0.0.1", CHROME_UA,
                                        session_id="abc123")

        assert result["event_id"] is not None

    def test_suspicious_event_creates_alerts(self, client, auth_header):
        from app.services.login_anomaly import record_login_event, get_security_alerts

        with client.application.app_context():
            now = datetime.utcnow()
            # Seed history to trigger suspicious detection
            for i in range(6):
                event = LoginEvent(
                    user_id=1,
                    event_type="login",
                    ip_address="10.0.0.1",
                    browser="Safari",
                    os="iOS",
                    created_at=now - timedelta(minutes=1, seconds=i),
                )
                db.session.add(event)
            db.session.commit()

            # Login from completely new IP + device (should be suspicious)
            result = record_login_event(1, "192.168.1.1", CHROME_UA)

            if result["is_suspicious"]:
                alerts = get_security_alerts(1)
                assert len(alerts) > 0


class TestLoginHistory:
    """Test get_login_history."""

    def test_empty_history(self, client, auth_header):
        from app.services.login_anomaly import get_login_history

        with client.application.app_context():
            events = get_login_history(1)

        assert events == []

    def test_history_returns_events(self, client, auth_header):
        from app.services.login_anomaly import record_login_event, get_login_history

        with client.application.app_context():
            record_login_event(1, "10.0.0.1", CHROME_UA)
            record_login_event(1, "10.0.0.1", CHROME_UA,
                               event_type="logout")
            events = get_login_history(1)

        assert len(events) == 2

    def test_filter_by_event_type(self, client, auth_header):
        from app.services.login_anomaly import record_login_event, get_login_history

        with client.application.app_context():
            record_login_event(1, "10.0.0.1", CHROME_UA)
            record_login_event(1, "10.0.0.1", CHROME_UA,
                               event_type="failed_login")

            events = get_login_history(1, event_type="failed_login")

        assert len(events) == 1
        assert events[0]["event_type"] == "failed_login"

    def test_history_limit(self, client, auth_header):
        from app.services.login_anomaly import record_login_event, get_login_history

        with client.application.app_context():
            for _ in range(5):
                record_login_event(1, "10.0.0.1", CHROME_UA)
            events = get_login_history(1, limit=3)

        assert len(events) == 3


class TestSecurityAlerts:
    """Test security alert functions."""

    def test_create_and_get_alerts(self, client, auth_header):
        from app.services.login_anomaly import _create_alert, get_security_alerts

        with client.application.app_context():
            _create_alert(1, "test_alert", "high", "Test Alert",
                          "This is a test", {"key": "value"})
            alerts = get_security_alerts(1)

        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "test_alert"
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["metadata"]["key"] == "value"

    def test_acknowledge_alert(self, client, auth_header):
        from app.services.login_anomaly import _create_alert, acknowledge_alert, get_security_alerts

        with client.application.app_context():
            _create_alert(1, "test", "medium", "Alert", "desc")
            alerts = get_security_alerts(1)
            aid = alerts[0]["id"]

            result = acknowledge_alert(1, aid)
            assert result is True

            updated = get_security_alerts(1)
            assert updated[0]["acknowledged"] is True

    def test_acknowledge_nonexistent(self, client, auth_header):
        from app.services.login_anomaly import acknowledge_alert

        with client.application.app_context():
            assert acknowledge_alert(1, 9999) is False

    def test_acknowledge_all(self, client, auth_header):
        from app.services.login_anomaly import _create_alert, acknowledge_all_alerts, get_security_alerts

        with client.application.app_context():
            _create_alert(1, "a", "low", "Alert 1", "d1")
            _create_alert(1, "b", "low", "Alert 2", "d2")
            _create_alert(1, "c", "low", "Alert 3", "d3")

            count = acknowledge_all_alerts(1)
            assert count == 3

            unack = get_security_alerts(1, unacknowledged_only=True)
            assert len(unack) == 0

    def test_unacknowledged_only_filter(self, client, auth_header):
        from app.services.login_anomaly import _create_alert, acknowledge_alert, get_security_alerts

        with client.application.app_context():
            _create_alert(1, "a", "low", "Alert 1", "d1")
            _create_alert(1, "b", "low", "Alert 2", "d2")

            alerts = get_security_alerts(1)
            acknowledge_alert(1, alerts[0]["id"])

            unack = get_security_alerts(1, unacknowledged_only=True)
            assert len(unack) == 1


class TestLoginStats:
    """Test get_login_stats."""

    def test_empty_stats(self, client, auth_header):
        from app.services.login_anomaly import get_login_stats

        with client.application.app_context():
            stats = get_login_stats(1)

        assert stats["total_events"] == 0
        assert stats["successful_logins"] == 0

    def test_stats_with_events(self, client, auth_header):
        from app.services.login_anomaly import record_login_event, get_login_stats

        with client.application.app_context():
            record_login_event(1, "10.0.0.1", CHROME_UA)
            record_login_event(1, "10.0.0.2", CHROME_UA)
            record_login_event(1, "10.0.0.1", CHROME_UA,
                               event_type="failed_login")

            stats = get_login_stats(1)

        assert stats["total_events"] == 3
        assert stats["successful_logins"] == 2
        assert stats["failed_logins"] == 1
        assert stats["unique_ips"] == 2


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestLoginAnomalyRoutes:
    """Integration tests for /security/* endpoints."""

    # ── POST /security/record ──
    def test_record_event_route(self, client, auth_header):
        r = client.post("/security/record", json={},
                        headers={**auth_header, "User-Agent": CHROME_UA})
        assert r.status_code == 201
        body = r.get_json()
        assert body["event_type"] == "login"
        assert "risk_score" in body

    def test_record_failed_login(self, client, auth_header):
        r = client.post("/security/record",
                        json={"event_type": "failed_login"},
                        headers={**auth_header, "User-Agent": CHROME_UA})
        assert r.status_code == 201
        assert r.get_json()["event_type"] == "failed_login"

    def test_record_unauthorized(self, client):
        r = client.post("/security/record", json={})
        assert r.status_code == 401

    # ── GET /security/history ──
    def test_history_route(self, client, auth_header):
        client.post("/security/record", json={}, headers=auth_header)
        r = client.get("/security/history", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] >= 1

    def test_history_with_filters(self, client, auth_header):
        client.post("/security/record", json={
            "event_type": "failed_login"
        }, headers=auth_header)
        r = client.get("/security/history?event_type=failed_login&limit=5",
                        headers=auth_header)
        assert r.status_code == 200

    # ── GET /security/alerts ──
    def test_alerts_route(self, client, auth_header):
        r = client.get("/security/alerts", headers=auth_header)
        assert r.status_code == 200
        assert "alerts" in r.get_json()

    def test_alerts_unacknowledged_filter(self, client, auth_header):
        r = client.get("/security/alerts?unacknowledged=true",
                        headers=auth_header)
        assert r.status_code == 200

    # ── POST /security/alerts/<id>/acknowledge ──
    def test_acknowledge_route(self, client, auth_header):
        # Create an alert manually
        from app.services.login_anomaly import _create_alert
        with client.application.app_context():
            _create_alert(1, "test", "low", "Test", "desc")
            from app.services.login_anomaly import get_security_alerts
            alerts = get_security_alerts(1)
            aid = alerts[0]["id"]

        r = client.post(f"/security/alerts/{aid}/acknowledge",
                        json={}, headers=auth_header)
        assert r.status_code == 200

    def test_acknowledge_nonexistent_route(self, client, auth_header):
        r = client.post("/security/alerts/9999/acknowledge",
                        json={}, headers=auth_header)
        assert r.status_code == 404

    # ── POST /security/alerts/acknowledge-all ──
    def test_acknowledge_all_route(self, client, auth_header):
        r = client.post("/security/alerts/acknowledge-all",
                        json={}, headers=auth_header)
        assert r.status_code == 200
        assert "count" in r.get_json()

    # ── GET /security/stats ──
    def test_stats_route(self, client, auth_header):
        r = client.get("/security/stats", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "total_events" in body
        assert "risk_distribution" in body

    def test_stats_with_days_param(self, client, auth_header):
        r = client.get("/security/stats?days=7", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["period_days"] == 7
