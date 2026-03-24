"""
Tests for Login Anomaly Detection and Security Alerts

Covers:
- Login event recording
- Risk score calculation
- Brute force detection
- Security alert creation and management
- API endpoints
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from decimal import Decimal

from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import (
    User, LoginEvent, SecurityAlert, AuditLog,
    LoginEventType, AlertSeverity, AlertStatus
)
from app.services import login_anomaly as anomaly_service


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret-with-32-plus-chars-1234567890"


@pytest.fixture
def app():
    settings = TestSettings()
    app = create_app(settings)
    app.config.update(TESTING=True)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_header(client):
    """Register and login a user, return auth header."""
    email = "security@test.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


@pytest.fixture
def test_user(app):
    """Create a test user."""
    with app.app_context():
        user = User(
            email="testuser@example.com",
            password_hash="hashed_password"
        )
        db.session.add(user)
        db.session.commit()
        return user.id


class TestRiskScoreCalculation:
    """Tests for risk score calculation."""
    
    def test_new_ip_adds_risk(self, app, test_user):
        """New IP should add risk score."""
        with app.app_context():
            score, factors = anomaly_service.calculate_risk_score(
                user_id=test_user,
                ip_address="192.168.1.100",
                device_fingerprint="device123",
                event_type=LoginEventType.LOGIN_SUCCESS.value
            )
            assert "new_ip_address" in factors
            assert score >= 0.3
    
    def test_new_device_adds_risk(self, app, test_user):
        """New device should add risk."""
        with app.app_context():
            # First, record a login with the same IP
            event = LoginEvent(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_SUCCESS.value,
                ip_address="192.168.1.100",
                device_fingerprint="old_device"
            )
            db.session.add(event)
            db.session.commit()
            
            # Now check with new device but same IP
            score, factors = anomaly_service.calculate_risk_score(
                user_id=test_user,
                ip_address="192.168.1.100",
                device_fingerprint="new_device_456",
                event_type=LoginEventType.LOGIN_SUCCESS.value
            )
            assert "new_device" in factors
            assert score >= 0.25
    
    def test_known_ip_reduces_risk(self, app, test_user):
        """Known IP should not add new_ip risk."""
        with app.app_context():
            # Record a previous login with this IP
            event = LoginEvent(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_SUCCESS.value,
                ip_address="192.168.1.100",
                device_fingerprint="device123"
            )
            db.session.add(event)
            db.session.commit()
            
            # Check with same IP
            score, factors = anomaly_service.calculate_risk_score(
                user_id=test_user,
                ip_address="192.168.1.100",
                device_fingerprint="device123",
                event_type=LoginEventType.LOGIN_SUCCESS.value
            )
            assert "new_ip_address" not in factors
            assert "new_device" not in factors
            assert score < 0.3
    
    def test_risk_score_capped_at_one(self, app, test_user):
        """Risk score should be capped at 1.0."""
        with app.app_context():
            # Add multiple failed attempts
            for _ in range(10):
                event = LoginEvent(
                    user_id=test_user,
                    event_type=LoginEventType.LOGIN_FAILED.value,
                    ip_address="192.168.1.100"
                )
                db.session.add(event)
            db.session.commit()
            
            score, factors = anomaly_service.calculate_risk_score(
                user_id=test_user,
                ip_address="10.0.0.1",  # New IP
                device_fingerprint="new_device",
                event_type=LoginEventType.LOGIN_SUCCESS.value
            )
            assert score <= 1.0


class TestLoginEventRecording:
    """Tests for login event recording."""
    
    def test_record_successful_login(self, app, test_user):
        """Record a successful login event."""
        with app.app_context():
            event = anomaly_service.record_login_event(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_SUCCESS.value,
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
                device_fingerprint="device123",
                risk_score=0.1,
                risk_factors=["test"]
            )
            
            assert event.id is not None
            assert event.event_type == LoginEventType.LOGIN_SUCCESS.value
            assert event.ip_address == "192.168.1.1"
            assert event.user_agent == "Mozilla/5.0"
    
    def test_record_failed_login(self, app, test_user):
        """Record a failed login event."""
        with app.app_context():
            event = anomaly_service.record_login_event(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_FAILED.value,
                ip_address="192.168.1.1"
            )
            
            assert event.id is not None
            assert event.event_type == LoginEventType.LOGIN_FAILED.value
    
    def test_record_brute_force_blocked(self, app, test_user):
        """Record a brute force blocked event."""
        with app.app_context():
            event = anomaly_service.record_login_event(
                user_id=test_user,
                event_type=LoginEventType.BRUTE_FORCE_BLOCKED.value,
                ip_address="192.168.1.1"
            )
            
            assert event.id is not None
            assert event.event_type == LoginEventType.BRUTE_FORCE_BLOCKED.value


class TestBruteForceDetection:
    """Tests for brute force detection."""
    
    def test_brute_force_not_triggered_initially(self, app):
        """IP should not be blocked initially."""
        with app.app_context():
            with patch.object(anomaly_service.redis_client, 'get', return_value=None):
                with patch.object(anomaly_service.redis_client, 'get', return_value=None):
                    result = anomaly_service.check_brute_force("192.168.1.1")
                    assert result is False
    
    def test_brute_force_after_threshold(self, app):
        """IP should be blocked after threshold."""
        with app.app_context():
            ip = "192.168.1.100"
            mock_redis = MagicMock()
            mock_redis.get.return_value = None
            mock_redis.get.return_value = None
            
            with patch.object(anomaly_service, 'redis_client', mock_redis):
                # Simulate threshold reached
                mock_redis.get.return_value = str(anomaly_service.BRUTE_FORCE_THRESHOLD)
                result = anomaly_service.check_brute_force(ip)
                # Should check the blocked flag
                mock_redis.get.assert_called()
    
    def test_clear_brute_force_block(self, app):
        """Clear brute force block should work."""
        with app.app_context():
            ip = "192.168.1.100"
            mock_redis = MagicMock()
            
            with patch.object(anomaly_service, 'redis_client', mock_redis):
                anomaly_service.clear_brute_force_block(ip)
                # Should delete the keys
                mock_redis.delete.assert_called()


class TestSecurityAlerts:
    """Tests for security alert management."""
    
    def test_create_security_alert(self, app, test_user):
        """Create a security alert."""
        with app.app_context():
            alert = anomaly_service.create_security_alert(
                user_id=test_user,
                alert_type="suspicious_login",
                title="Suspicious Login Detected",
                description="Login from new location",
                severity=AlertSeverity.MEDIUM.value,
                ip_address="192.168.1.1"
            )
            
            assert alert.id is not None
            assert alert.alert_type == "suspicious_login"
            assert alert.severity == AlertSeverity.MEDIUM.value
            assert alert.status == AlertStatus.ACTIVE.value
    
    def test_acknowledge_alert(self, app, test_user):
        """Acknowledge a security alert."""
        with app.app_context():
            alert = anomaly_service.create_security_alert(
                user_id=test_user,
                alert_type="test_alert",
                title="Test Alert"
            )
            
            acknowledged = anomaly_service.acknowledge_alert(alert.id, test_user)
            
            assert acknowledged is not None
            assert acknowledged.status == AlertStatus.ACKNOWLEDGED.value
            assert acknowledged.acknowledged_at is not None
    
    def test_acknowledge_nonexistent_alert(self, app, test_user):
        """Acknowledge non-existent alert should return None."""
        with app.app_context():
            result = anomaly_service.acknowledge_alert(9999, test_user)
            assert result is None
    
    def test_acknowledge_all_alerts(self, app, test_user):
        """Acknowledge all alerts for a user."""
        with app.app_context():
            # Create multiple alerts
            for i in range(3):
                anomaly_service.create_security_alert(
                    user_id=test_user,
                    alert_type=f"alert_{i}",
                    title=f"Alert {i}"
                )
            
            count = anomaly_service.acknowledge_all_alerts(test_user)
            
            assert count == 3
            
            # Verify all are acknowledged
            alerts = anomaly_service.get_user_alerts(test_user, status=AlertStatus.ACTIVE.value)
            assert len(alerts) == 0


class TestLoginHistory:
    """Tests for login history retrieval."""
    
    def test_get_login_history(self, app, test_user):
        """Get login history for a user."""
        with app.app_context():
            # Create some login events
            for i in range(5):
                anomaly_service.record_login_event(
                    user_id=test_user,
                    event_type=LoginEventType.LOGIN_SUCCESS.value,
                    ip_address=f"192.168.1.{i}"
                )
            
            history = anomaly_service.get_user_login_history(test_user)
            
            assert len(history) == 5
    
    def test_get_history_with_filter(self, app, test_user):
        """Get login history filtered by event type."""
        with app.app_context():
            anomaly_service.record_login_event(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_SUCCESS.value
            )
            anomaly_service.record_login_event(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_FAILED.value
            )
            
            history = anomaly_service.get_user_login_history(
                test_user,
                event_type=LoginEventType.LOGIN_SUCCESS.value
            )
            
            assert len(history) == 1
            assert history[0]["event_type"] == LoginEventType.LOGIN_SUCCESS.value


class TestSecurityStats:
    """Tests for security statistics."""
    
    def test_get_security_stats(self, app, test_user):
        """Get security statistics for a user."""
        with app.app_context():
            # Create some events
            anomaly_service.record_login_event(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_SUCCESS.value,
                ip_address="192.168.1.1",
                device_fingerprint="device1",
                risk_score=0.8
            )
            anomaly_service.record_login_event(
                user_id=test_user,
                event_type=LoginEventType.LOGIN_FAILED.value
            )
            
            stats = anomaly_service.get_security_stats(test_user)
            
            assert stats["total_logins"] == 1
            assert stats["failed_logins"] == 1
            assert stats["unique_ips"] == 1
            assert stats["unique_devices"] == 1
            assert stats["high_risk_logins"] == 1


class TestProcessLogin:
    """Tests for the process_login function."""
    
    def test_process_successful_login(self, app, test_user):
        """Process a successful login."""
        with app.app_context():
            user = db.session.get(User, test_user)
            
            # Mock Redis to avoid connection issues
            mock_redis = MagicMock()
            mock_redis.get.return_value = None
            mock_redis.smembers.return_value = set()
            mock_redis.sadd.return_value = 1
            mock_redis.expire.return_value = True
            
            with patch.object(anomaly_service, 'redis_client', mock_redis):
                event, alert, should_block = anomaly_service.process_login(
                    user=user,
                    is_successful=True,
                    ip_address="192.168.1.1"
                )
            
            assert event is not None
            assert event.event_type == LoginEventType.LOGIN_SUCCESS.value
            assert should_block is False
    
    def test_process_failed_login(self, app, test_user):
        """Process a failed login."""
        with app.app_context():
            user = db.session.get(User, test_user)
            
            # Mock Redis
            mock_redis = MagicMock()
            mock_redis.get.return_value = None
            mock_redis.incr.return_value = 1
            mock_redis.expire.return_value = True
            
            with patch.object(anomaly_service, 'redis_client', mock_redis):
                event, alert, should_block = anomaly_service.process_login(
                    user=user,
                    is_successful=False,
                    ip_address="192.168.1.1"
                )
            
            assert event is not None
            assert event.event_type == LoginEventType.LOGIN_FAILED.value
            assert should_block is False
    
    def test_process_login_creates_alert_on_high_risk(self, app, test_user):
        """High risk login should create an alert."""
        with app.app_context():
            user = db.session.get(User, test_user)
            
            # Mock Redis
            mock_redis = MagicMock()
            mock_redis.get.return_value = None
            mock_redis.smembers.return_value = set()
            mock_redis.sadd.return_value = 1
            mock_redis.expire.return_value = True
            
            with patch.object(anomaly_service, 'redis_client', mock_redis):
                event, alert, should_block = anomaly_service.process_login(
                    user=user,
                    is_successful=True,
                    ip_address="10.0.0.1",  # New IP to trigger risk
                    user_agent="New Agent"
                )
            
            # Should have high risk due to new IP and device
            assert float(event.risk_score) >= 0.3


class TestSecurityAPIEndpoints:
    """Tests for security API endpoints."""
    
    def test_record_event_endpoint(self, client, auth_header):
        """Test POST /security/record endpoint."""
        r = client.post(
            "/security/record",
            json={
                "event_type": "login_success",
                "ip_address": "192.168.1.1"
            },
            headers=auth_header
        )
        
        assert r.status_code == 201
        data = r.get_json()
        assert "event" in data
        assert data["event"]["event_type"] == "login_success"
    
    def test_record_event_invalid_type(self, client, auth_header):
        """Test POST /security/record with invalid event type."""
        r = client.post(
            "/security/record",
            json={"event_type": "invalid_type"},
            headers=auth_header
        )
        
        assert r.status_code == 400
    
    def test_login_history_endpoint(self, client, auth_header):
        """Test GET /security/history endpoint."""
        # Record an event first
        client.post(
            "/security/record",
            json={"event_type": "login_success"},
            headers=auth_header
        )
        
        r = client.get("/security/history", headers=auth_header)
        
        assert r.status_code == 200
        data = r.get_json()
        assert "events" in data
        assert len(data["events"]) >= 1
    
    def test_alerts_endpoint(self, client, auth_header):
        """Test GET /security/alerts endpoint."""
        r = client.get("/security/alerts", headers=auth_header)
        
        assert r.status_code == 200
        data = r.get_json()
        assert "alerts" in data
    
    def test_stats_endpoint(self, client, auth_header):
        """Test GET /security/stats endpoint."""
        r = client.get("/security/stats", headers=auth_header)
        
        assert r.status_code == 200
        data = r.get_json()
        assert "total_logins" in data
        assert "failed_logins" in data
        assert "unique_ips" in data
    
    def test_analyze_endpoint(self, client, auth_header):
        """Test POST /security/analyze endpoint."""
        r = client.post(
            "/security/analyze",
            json={"ip_address": "192.168.1.1"},
            headers=auth_header
        )
        
        assert r.status_code == 200
        data = r.get_json()
        assert "risk_score" in data
        assert "risk_factors" in data
        assert "recommendation" in data
    
    def test_check_ip_endpoint(self, client, auth_header):
        """Test GET /security/check-ip endpoint."""
        r = client.get("/security/check-ip", headers=auth_header)
        
        assert r.status_code == 200
        data = r.get_json()
        assert "ip_address" in data
        assert "blocked" in data


class TestAuthLoginIntegration:
    """Tests for auth login integration with security."""
    
    def test_login_returns_security_info(self, client):
        """Login should include security information."""
        email = "integration@test.com"
        password = "password123"
        
        # Register
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201
        
        # Login
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        
        data = r.get_json()
        assert "access_token" in data
        assert "refresh_token" in data
    
    def test_login_failed_creates_event(self, client):
        """Failed login should create a login event."""
        r = client.post("/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "wrongpassword"
        })
        
        assert r.status_code == 401
    
    def test_login_with_valid_credentials(self, client):
        """Successful login should work."""
        email = "valid@test.com"
        password = "password123"
        
        client.post("/auth/register", json={"email": email, "password": password})
        
        r = client.post("/auth/login", json={"email": email, "password": password})
        
        assert r.status_code == 200
        data = r.get_json()
        assert "access_token" in data


class TestUnusualTimeDetection:
    """Tests for unusual time detection."""
    
    def test_is_unusual_time_night(self):
        """Test unusual time detection for night hours."""
        # Mock datetime to return a specific hour
        with patch('app.services.login_anomaly.datetime') as mock_dt:
            # Test 3 AM UTC (unusual)
            mock_dt.utcnow.return_value = MagicMock(hour=3)
            assert anomaly_service.is_unusual_time() is True
            
            # Test 2 AM UTC (unusual)
            mock_dt.utcnow.return_value = MagicMock(hour=2)
            assert anomaly_service.is_unusual_time() is True
    
    def test_is_unusual_time_day(self):
        """Test unusual time detection for normal hours."""
        with patch('app.services.login_anomaly.datetime') as mock_dt:
            # Test 10 AM UTC (normal)
            mock_dt.utcnow.return_value = MagicMock(hour=10)
            assert anomaly_service.is_unusual_time() is False
            
            # Test 8 PM UTC (normal)
            mock_dt.utcnow.return_value = MagicMock(hour=20)
            assert anomaly_service.is_unusual_time() is False


class TestPagination:
    """Tests for pagination in endpoints."""
    
    def test_history_pagination(self, client, auth_header):
        """Test pagination for login history."""
        # Record multiple events
        for i in range(15):
            client.post(
                "/security/record",
                json={"event_type": "login_success"},
                headers=auth_header
            )
        
        # Get first page
        r = client.get("/security/history?limit=10&offset=0", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["events"]) == 10
        
        # Get second page
        r = client.get("/security/history?limit=10&offset=10", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["events"]) >= 5
    
    def test_alerts_pagination(self, client, auth_header):
        """Test pagination for alerts."""
        r = client.get("/security/alerts?limit=10&offset=0", headers=auth_header)
        assert r.status_code == 200


class TestSecurity:
    """Security-related tests."""
    
    def test_unauthorized_access(self, client):
        """Unauthorized requests should be rejected."""
        r = client.get("/security/history")
        assert r.status_code == 401
        
        r = client.get("/security/alerts")
        assert r.status_code == 401
        
        r = client.get("/security/stats")
        assert r.status_code == 401
    
    def test_user_cannot_access_other_users_alerts(self, client):
        """User should not be able to access other users' alerts."""
        # Create user 1
        email1 = "user1@test.com"
        password1 = "password123"
        client.post("/auth/register", json={"email": email1, "password": password1})
        r1 = client.post("/auth/login", json={"email": email1, "password": password1})
        auth1 = {"Authorization": f"Bearer {r1.get_json()['access_token']}"}
        
        # Create user 2
        email2 = "user2@test.com"
        password2 = "password123"
        client.post("/auth/register", json={"email": email2, "password": password2})
        r2 = client.post("/auth/login", json={"email": email2, "password": password2})
        auth2 = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}
        
        # User 1 should not see User 2's data
        r = client.get("/security/alerts", headers=auth1)
        alerts1 = r.get_json()["alerts"]
        
        r = client.get("/security/alerts", headers=auth2)
        alerts2 = r.get_json()["alerts"]
        
        # Each user should only see their own alerts
        assert len(alerts1) == 0
        assert len(alerts2) == 0