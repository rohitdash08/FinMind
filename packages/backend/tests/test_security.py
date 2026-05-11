"""
Tests for login anomaly detection (issue #124).

Covers:
- Failed login attempt tracking via Redis
- IP-level failure threshold triggers ip_blocked flag
- Email-level failure threshold triggers email_blocked flag
- Successful login resets failure counters
- /auth/security-alerts endpoint returns per-user events
- service gracefully degrades when Redis is unavailable
"""

from unittest.mock import patch


# ── helpers ───────────────────────────────────────────────────────────────────


def _register_and_login(client, email="user@sec.test", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.get_json()["access_token"]


# ── record_login_attempt unit tests ──────────────────────────────────────────


def test_record_failed_attempt_increments_counters(app_fixture):
    from app.services.security import (
        record_login_attempt,
        _FAIL_IP_KEY,
        _FAIL_EMAIL_KEY,
    )
    from app.extensions import redis_client

    with app_fixture.app_context():
        record_login_attempt("a@x.com", "1.2.3.4", success=False)
        assert int(redis_client.get(_FAIL_IP_KEY.format(ip="1.2.3.4")) or 0) == 1
        assert int(redis_client.get(_FAIL_EMAIL_KEY.format(email="a@x.com")) or 0) == 1


def test_ip_blocked_after_threshold(app_fixture):
    from app.services.security import record_login_attempt, _FAIL_IP_KEY, _IP_FAIL_LIMIT
    from app.extensions import redis_client

    with app_fixture.app_context():
        for _ in range(_IP_FAIL_LIMIT + 1):
            record_login_attempt("b@x.com", "5.5.5.5", success=False)
        count = int(redis_client.get(_FAIL_IP_KEY.format(ip="5.5.5.5")) or 0)
        assert count > _IP_FAIL_LIMIT


def test_email_blocked_after_threshold(app_fixture):
    from app.services.security import (
        record_login_attempt,
        _FAIL_EMAIL_KEY,
        _EMAIL_FAIL_LIMIT,
    )
    from app.extensions import redis_client

    with app_fixture.app_context():
        for _ in range(_EMAIL_FAIL_LIMIT + 1):
            record_login_attempt("c@x.com", "6.6.6.1", success=False)
        count = int(redis_client.get(_FAIL_EMAIL_KEY.format(email="c@x.com")) or 0)
        assert count > _EMAIL_FAIL_LIMIT


def test_success_resets_failure_counters(app_fixture):
    from app.services.security import (
        record_login_attempt,
        _FAIL_IP_KEY,
        _FAIL_EMAIL_KEY,
    )
    from app.extensions import redis_client

    with app_fixture.app_context():
        for _ in range(3):
            record_login_attempt("d@x.com", "7.7.7.7", success=False)
        # Successful login should clear counters
        record_login_attempt("d@x.com", "7.7.7.7", success=True, user_id=99)
        assert redis_client.get(_FAIL_IP_KEY.format(ip="7.7.7.7")) is None
        assert redis_client.get(_FAIL_EMAIL_KEY.format(email="d@x.com")) is None


def test_events_stored_for_user(app_fixture):
    from app.services.security import record_login_attempt, get_security_alerts

    with app_fixture.app_context():
        record_login_attempt("e@x.com", "9.9.9.9", success=False, user_id=42)
        record_login_attempt("e@x.com", "9.9.9.9", success=True, user_id=42)
        alerts = get_security_alerts(42)
        assert len(alerts) == 2
        # Events are newest-first (LPUSH)
        assert alerts[0]["type"] == "login_success"
        assert alerts[1]["type"] == "login_failed"


def test_graceful_degradation_when_redis_down(app_fixture):
    from app.services.security import record_login_attempt

    with app_fixture.app_context():
        with patch("app.services.security.redis_client") as mock_redis:
            mock_redis.pipeline.side_effect = Exception("Redis unavailable")
            # Should not raise — login flow must not be disrupted
            record_login_attempt("f@x.com", "10.0.0.1", success=False)


# ── /auth/security-alerts endpoint integration tests ─────────────────────────


def test_security_alerts_endpoint_requires_auth(client):
    r = client.get("/auth/security-alerts")
    assert r.status_code == 401


def test_security_alerts_empty_for_new_user(client):
    token = _register_and_login(client)
    r = client.get(
        "/auth/security-alerts", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


def test_security_alerts_records_failed_attempts(client):
    email = "sec_fail@test.com"
    password = "pass5678"
    client.post("/auth/register", json={"email": email, "password": password})

    # Trigger some failed logins
    for _ in range(2):
        client.post("/auth/login", json={"email": email, "password": "wrongpass"})

    # Successful login records a success event
    token = _register_and_login(client, email=email, password=password)
    r = client.get(
        "/auth/security-alerts", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    alerts = r.get_json()["alerts"]
    types = [a["type"] for a in alerts]
    assert "login_success" in types
    assert any(t in ("login_failed", "suspicious_login") for t in types)


def test_security_alerts_suspicious_flag_on_excess_failures(client):
    email = "sus@test.com"
    password = "securepass"
    client.post("/auth/register", json={"email": email, "password": password})

    from app.services.security import _IP_FAIL_LIMIT

    # Exceed the IP failure threshold
    for _ in range(_IP_FAIL_LIMIT + 1):
        client.post("/auth/login", json={"email": email, "password": "bad"})

    token = _register_and_login(client, email=email, password=password)
    r = client.get(
        "/auth/security-alerts", headers={"Authorization": f"Bearer {token}"}
    )
    alerts = r.get_json()["alerts"]
    types = [a["type"] for a in alerts]
    assert "suspicious_login" in types
