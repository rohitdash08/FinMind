"""Tests for login anomaly detection feature."""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import patch
from app.models import LoginAttempt, LoginAnomaly, AnomalyType, AnomalySeverity, User
from app.extensions import db, redis_client
from app.services.login_anomaly import (
    record_login_attempt,
    detect_anomalies,
    is_account_locked,
    get_lockout_remaining,
    set_account_lockout,
    clear_account_lockout,
    get_user_anomalies,
    resolve_anomaly,
    get_login_history,
    get_security_summary,
    FAILED_ATTEMPT_THRESHOLD,
    LOCKOUT_THRESHOLD,
)


class TestLoginAttemptRecording:
    """Tests for login attempt recording."""

    def test_record_successful_login(self, app_fixture, auth_header, client):
        """Test that successful logins are recorded."""
        # Get user id from auth_header login
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email="test@example.com").first()
            
            # Record a successful login
            attempt = record_login_attempt(
                user_id=user.id,
                email=user.email,
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0 Test Browser",
                success=True,
            )
            
            assert attempt.id is not None
            assert attempt.user_id == user.id
            assert attempt.success is True
            assert attempt.ip_address == "192.168.1.1"

    def test_record_failed_login(self, app_fixture):
        """Test that failed logins are recorded."""
        with app_fixture.app_context():
            attempt = record_login_attempt(
                user_id=None,
                email="unknown@test.com",
                ip_address="10.0.0.1",
                user_agent="Test Agent",
                success=False,
            )
            
            assert attempt.id is not None
            assert attempt.user_id is None
            assert attempt.success is False


class TestBruteForceDetection:
    """Tests for brute force attack detection."""

    def test_brute_force_detection_triggers_after_threshold(self, app_fixture, client):
        """Test that brute force is detected after threshold failures."""
        email = "bruteforce@test.com"
        password = "secret123"
        
        # Register user
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            # Simulate multiple failed login attempts
            for i in range(FAILED_ATTEMPT_THRESHOLD):
                record_login_attempt(
                    user_id=user.id,
                    email=email,
                    ip_address="10.0.0.1",
                    user_agent="Attacker Bot",
                    success=False,
                )
            
            # Check that a brute force anomaly was created
            anomalies = get_user_anomalies(user.id)
            brute_force_anomalies = [
                a for a in anomalies if a.anomaly_type == AnomalyType.BRUTE_FORCE
            ]
            assert len(brute_force_anomalies) >= 1

    def test_account_lockout_after_too_many_failures(self, app_fixture, client):
        """Test that account gets locked after lockout threshold."""
        email = "lockout@test.com"
        password = "secret123"
        
        # Register user
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            # Simulate lockout threshold failures
            for i in range(LOCKOUT_THRESHOLD):
                record_login_attempt(
                    user_id=user.id,
                    email=email,
                    ip_address="10.0.0.1",
                    user_agent="Attacker Bot",
                    success=False,
                )
            
            # Check that account is locked
            assert is_account_locked(user.id) is True
            assert get_lockout_remaining(user.id) is not None
            assert get_lockout_remaining(user.id) > 0

    def test_login_blocked_when_locked(self, client):
        """Test that login returns 423 when account is locked."""
        email = "locked@test.com"
        password = "secret123"
        
        # Register user
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        # Simulate many failed attempts via the API
        for i in range(LOCKOUT_THRESHOLD + 1):
            client.post("/auth/login", json={"email": email, "password": "wrongpass"})
        
        # Now even with correct password, should be locked
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 423
        data = r.get_json()
        assert "lockout_remaining_seconds" in data


class TestNewIPDetection:
    """Tests for new IP address detection."""

    def test_new_ip_not_flagged_on_first_login(self, app_fixture, client):
        """Test that first login doesn't trigger new IP alert."""
        email = "newip1@test.com"
        password = "secret123"
        
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="1.1.1.1",
                user_agent="Browser",
                success=True,
            )
            
            anomalies = get_user_anomalies(user.id)
            new_ip_anomalies = [
                a for a in anomalies if a.anomaly_type == AnomalyType.NEW_IP
            ]
            assert len(new_ip_anomalies) == 0

    def test_new_ip_flagged_on_second_different_ip(self, app_fixture, client):
        """Test that login from new IP triggers alert after first login."""
        email = "newip2@test.com"
        password = "secret123"
        
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            # First login from IP A
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="1.1.1.1",
                user_agent="Browser",
                success=True,
            )
            
            # Second login from IP B
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="2.2.2.2",
                user_agent="Browser",
                success=True,
            )
            
            anomalies = get_user_anomalies(user.id)
            new_ip_anomalies = [
                a for a in anomalies if a.anomaly_type == AnomalyType.NEW_IP
            ]
            assert len(new_ip_anomalies) == 1


class TestNewDeviceDetection:
    """Tests for new device detection."""

    def test_new_device_detected(self, app_fixture, client):
        """Test that new device is detected."""
        email = "newdevice@test.com"
        password = "secret123"
        
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            # First login from device A
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="1.1.1.1",
                user_agent="Mozilla/5.0 Chrome/100",
                success=True,
            )
            
            # Second login from device B (different user agent)
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="1.1.1.1",
                user_agent="Mozilla/5.0 Firefox/90",
                success=True,
            )
            
            anomalies = get_user_anomalies(user.id)
            new_device_anomalies = [
                a for a in anomalies if a.anomaly_type == AnomalyType.NEW_DEVICE
            ]
            assert len(new_device_anomalies) == 1


class TestUnusualTimeDetection:
    """Tests for unusual login time detection."""

    def test_unusual_time_detected(self, app_fixture, client):
        """Test that login at unusual hours is detected."""
        email = "unusualtime@test.com"
        password = "secret123"
        
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            # First login at normal time
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="1.1.1.1",
                user_agent="Browser",
                success=True,
            )
            
            # Manually create a login attempt at 3 AM
            unusual_time = datetime.utcnow().replace(hour=3, minute=0)
            attempt = LoginAttempt(
                user_id=user.id,
                email=email,
                ip_address="1.1.1.1",
                user_agent="Browser",
                device_fingerprint="test",
                success=True,
                created_at=unusual_time,
            )
            db.session.add(attempt)
            db.session.commit()
            
            # Trigger anomaly detection manually
            from app.services.login_anomaly import detect_anomalies
            detect_anomalies(user.id, attempt)
            
            anomalies = get_user_anomalies(user.id)
            unusual_time_anomalies = [
                a for a in anomalies if a.anomaly_type == AnomalyType.UNUSUAL_TIME
            ]
            assert len(unusual_time_anomalies) == 1


class TestSecurityEndpoints:
    """Tests for security-related API endpoints."""

    def test_security_summary_endpoint(self, client, auth_header):
        """Test the security summary endpoint."""
        r = client.get("/auth/security/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        
        assert "unresolved_anomalies" in data
        assert "recent_anomalies_7d" in data
        assert "failed_logins_24h" in data
        assert "unique_ips_30d" in data
        assert "account_locked" in data

    def test_login_history_endpoint(self, client, auth_header):
        """Test the login history endpoint."""
        r = client.get("/auth/security/login-history", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        
        assert "login_history" in data
        assert isinstance(data["login_history"], list)

    def test_anomalies_endpoint(self, client, auth_header):
        """Test the anomalies endpoint."""
        r = client.get("/auth/security/anomalies", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        
        assert "anomalies" in data
        assert isinstance(data["anomalies"], list)

    def test_resolve_anomaly(self, app_fixture, client, auth_header):
        """Test resolving an anomaly."""
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email="test@example.com").first()
            
            # Create a test anomaly
            anomaly = LoginAnomaly(
                user_id=user.id,
                anomaly_type=AnomalyType.NEW_IP,
                severity=AnomalySeverity.MEDIUM,
                description="Test anomaly",
            )
            db.session.add(anomaly)
            db.session.commit()
            anomaly_id = anomaly.id
        
        # Resolve the anomaly
        r = client.post(
            f"/auth/security/anomalies/{anomaly_id}/resolve",
            json={"note": "This was me"},
            headers=auth_header,
        )
        assert r.status_code == 200
        
        # Verify it's resolved
        r = client.get("/auth/security/anomalies?unresolved=true", headers=auth_header)
        data = r.get_json()
        resolved_ids = [a["id"] for a in data["anomalies"]]
        assert anomaly_id not in resolved_ids

    def test_resolve_nonexistent_anomaly(self, client, auth_header):
        """Test resolving a non-existent anomaly returns 404."""
        r = client.post(
            "/auth/security/anomalies/99999/resolve",
            json={},
            headers=auth_header,
        )
        assert r.status_code == 404


class TestLoginWithAnomalyWarnings:
    """Tests for login responses with security warnings."""

    def test_login_returns_security_warnings(self, app_fixture, client):
        """Test that login returns security warnings when anomalies exist."""
        email = "warnings@test.com"
        password = "secret123"
        
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            # Create an unresolved anomaly
            anomaly = LoginAnomaly(
                user_id=user.id,
                anomaly_type=AnomalyType.BRUTE_FORCE,
                severity=AnomalySeverity.HIGH,
                description="Multiple failed login attempts",
            )
            db.session.add(anomaly)
            db.session.commit()
        
        # Login and check for warnings
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        data = r.get_json()
        
        assert "access_token" in data
        assert "security_warnings" in data
        assert len(data["security_warnings"]) >= 1
        assert data["security_warnings"][0]["type"] == "BRUTE_FORCE"


class TestAccountUnlock:
    """Tests for account unlock functionality."""

    def test_self_unlock_clears_lockout(self, app_fixture, client):
        """Test that users can self-unlock their account."""
        email = "unlock@test.com"
        password = "secret123"
        
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            set_account_lockout(user.id)
            assert is_account_locked(user.id) is True
        
        # Get access token first (need to clear lockout to login)
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            clear_account_lockout(user.id)
        
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        access_token = r.get_json()["access_token"]
        
        # Re-lock the account
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            set_account_lockout(user.id)
        
        # Now unlock via endpoint
        r = client.post(
            "/auth/security/unlock",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert r.status_code == 200
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            assert is_account_locked(user.id) is False


class TestImpossibleTravel:
    """Tests for impossible travel detection."""

    def test_rapid_ip_change_detected(self, app_fixture, client):
        """Test that rapid login from different IPs is detected."""
        email = "travel@test.com"
        password = "secret123"
        
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code in (201, 409)
        
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email=email).first()
            
            # Login from IP A
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="1.1.1.1",
                user_agent="Browser",
                success=True,
            )
            
            # Immediately login from IP B (within threshold)
            record_login_attempt(
                user_id=user.id,
                email=email,
                ip_address="2.2.2.2",
                user_agent="Browser",
                success=True,
            )
            
            anomalies = get_user_anomalies(user.id)
            travel_anomalies = [
                a for a in anomalies if a.anomaly_type == AnomalyType.IMPOSSIBLE_TRAVEL
            ]
            assert len(travel_anomalies) == 1
            assert travel_anomalies[0].severity == AnomalySeverity.HIGH
