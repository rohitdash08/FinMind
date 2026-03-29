"""Tests for login anomaly detection."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import json

from app import create_app
from app.extensions import db
from app.models import (
    User,
    LoginAttempt,
    UserDevice,
    LoginAnomaly,
    LoginAnomalyType,
)
from app.services.login_anomaly import (
    LoginAnomalyDetector,
    LoginContext,
    AnomalyResult,
    get_client_ip,
)


class FakeRedis:
    """Fake Redis client for testing."""
    def __init__(self):
        self.data = {}
    
    def get(self, key):
        return self.data.get(key)
    
    def setex(self, key, ttl, value):
        self.data[key] = value
    
    def delete(self, key):
        self.data.pop(key, None)
    
    def flushdb(self):
        self.data.clear()


@pytest.fixture
def fake_redis():
    """Create fake Redis client."""
    return FakeRedis()


@pytest.fixture
def app(fake_redis):
    """Create test app with in-memory database and fake Redis."""
    from app.config import Settings
    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="test-secret-with-32-plus-chars-1234567890",
    )
    app = create_app(settings)
    
    # Patch redis_client at module level
    import app.extensions as ext
    import app.routes.auth as auth_mod
    original_redis = ext.redis_client
    original_auth_redis = auth_mod.redis_client
    
    ext.redis_client = fake_redis
    auth_mod.redis_client = fake_redis
    
    with app.app_context():
        db.create_all()
        yield app
    
    # Restore
    ext.redis_client = original_redis
    auth_mod.redis_client = original_auth_redis


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def detector_instance():
    """Create detector instance."""
    return LoginAnomalyDetector()


class TestLoginContext:
    """Tests for LoginContext dataclass."""
    
    def test_create_context(self):
        context = LoginContext(
            user_id=1,
            email="test@example.com",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            device_fingerprint="abc123",
            country="US",
            city="New York",
        )
        assert context.user_id == 1
        assert context.email == "test@example.com"
        assert context.ip_address == "192.168.1.1"


class TestAnomalyResult:
    """Tests for AnomalyResult dataclass."""
    
    def test_no_anomaly(self):
        result = AnomalyResult(is_anomaly=False)
        assert result.is_anomaly is False
        assert result.anomaly_type is None
    
    def test_with_anomaly(self):
        result = AnomalyResult(
            is_anomaly=True,
            anomaly_type=LoginAnomalyType.NEW_DEVICE,
            severity="medium",
            details={"device": "test"}
        )
        assert result.is_anomaly is True
        assert result.anomaly_type == LoginAnomalyType.NEW_DEVICE


class TestLoginAnomalyDetector:
    """Tests for LoginAnomalyDetector class."""
    
    def test_device_fingerprint_generation(self, detector_instance):
        fp1 = detector_instance.detect_device_fingerprint("Chrome/1.0", "192.168.1.1")
        fp2 = detector_instance.detect_device_fingerprint("Chrome/1.0", "192.168.1.1")
        assert fp1 == fp2
        assert len(fp1) == 32
    
    def test_different_devices_different_fingerprints(self, detector_instance):
        fp1 = detector_instance.detect_device_fingerprint("Chrome/1.0", "192.168.1.1")
        fp2 = detector_instance.detect_device_fingerprint("Firefox/1.0", "192.168.1.1")
        assert fp1 != fp2
    
    def test_record_login_attempt(self, app, detector_instance):
        with app.app_context():
            context = LoginContext(
                user_id=1,
                email="test@example.com",
                ip_address="192.168.1.1",
                user_agent="Test Agent",
                device_fingerprint="abc123",
            )
            attempt = detector_instance.record_login_attempt(context, success=True)
            db.session.commit()
            assert attempt.id is not None
            assert attempt.email == "test@example.com"
            assert attempt.success is True
    
    def test_check_new_device_no_user(self, app, detector_instance):
        with app.app_context():
            context = LoginContext(
                user_id=None,
                email="test@example.com",
                ip_address="192.168.1.1",
                device_fingerprint="abc123",
            )
            result = detector_instance.check_new_device(context)
            assert result.is_anomaly is False
    
    def test_check_new_device_first_device(self, app, detector_instance):
        with app.app_context():
            user = User(email="test@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()
            context = LoginContext(
                user_id=user.id,
                email="test@example.com",
                ip_address="192.168.1.1",
                device_fingerprint="abc123",
            )
            result = detector_instance.check_new_device(context)
            assert result.is_anomaly is True
            assert result.anomaly_type == LoginAnomalyType.NEW_DEVICE
    
    def test_check_new_device_known_device(self, app, detector_instance):
        with app.app_context():
            user = User(email="test@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()
            device = UserDevice(
                user_id=user.id,
                device_fingerprint="abc123",
                ip_address="192.168.1.1",
            )
            db.session.add(device)
            db.session.commit()
            context = LoginContext(
                user_id=user.id,
                email="test@example.com",
                ip_address="192.168.1.1",
                device_fingerprint="abc123",
            )
            result = detector_instance.check_new_device(context)
            assert result.is_anomaly is False
    
    def test_check_new_location_different_country(self, app, detector_instance):
        with app.app_context():
            user = User(email="test@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()
            attempt = LoginAttempt(
                user_id=user.id,
                email="test@example.com",
                ip_address="192.168.1.1",
                success=True,
                country="US",
            )
            db.session.add(attempt)
            db.session.commit()
            context = LoginContext(
                user_id=user.id,
                email="test@example.com",
                ip_address="10.0.0.1",
                country="CN",
                city="Beijing",
            )
            result = detector_instance.check_new_location(context)
            assert result.is_anomaly is True
            assert result.anomaly_type == LoginAnomalyType.NEW_LOCATION
    
    def test_check_multiple_failures_at_threshold(self, app, detector_instance):
        with app.app_context():
            for _ in range(5):
                attempt = LoginAttempt(
                    user_id=None,
                    email="test@example.com",
                    ip_address="192.168.1.1",
                    success=False,
                    failure_reason="invalid_credentials",
                )
                db.session.add(attempt)
            db.session.commit()
            result = detector_instance.check_multiple_failures("test@example.com")
            assert result.is_anomaly is True
            assert result.anomaly_type == LoginAnomalyType.MULTIPLE_FAILURES
    
    def test_check_suspicious_ip_private(self, app, detector_instance):
        """Test that private IPs are flagged as suspicious."""
        with app.app_context():
            context = LoginContext(
                user_id=None,
                email="test@example.com",
                ip_address="192.168.1.1",
            )
            result = detector_instance.check_suspicious_ip(context)
            assert result.is_anomaly is True
            assert result.anomaly_type == LoginAnomalyType.SUSPICIOUS_IP
            assert result.details["reason"] == "private_or_internal_ip"
    
    def test_check_suspicious_ip_public(self, app, detector_instance):
        """Test that public IPs are not flagged as suspicious."""
        with app.app_context():
            context = LoginContext(
                user_id=None,
                email="test@example.com",
                ip_address="8.8.8.8",  # Google's public DNS
            )
            result = detector_instance.check_suspicious_ip(context)
            assert result.is_anomaly is False
    
    def test_process_login_success(self, app, detector_instance):
        with app.app_context():
            user = User(email="test@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()
            context = LoginContext(
                user_id=user.id,
                email="test@example.com",
                ip_address="8.8.8.8",  # Use public IP to avoid SUSPICIOUS_IP detection
                user_agent="Test Agent",
            )
            attempt, anomalies = detector_instance.process_login(context, success=True)
            db.session.commit()
            assert attempt.id is not None
            assert attempt.success is True
            assert len(anomalies) == 1  # Only new_device, no suspicious_ip for public IP
            device = db.session.query(UserDevice).filter(
                UserDevice.user_id == user.id
            ).first()
            assert device is not None


class TestSecurityEndpoints:
    """Tests for security API endpoints."""
    
    @pytest.fixture
    def auth_header(self, client):
        client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "password123"
        })
        response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "password123"
        })
        data = response.get_json()
        return {"Authorization": f"Bearer {data['access_token']}"}
    
    def test_list_devices_after_login(self, client, auth_header):
        response = client.get("/security/devices", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 1
    
    def test_login_history(self, client, auth_header):
        response = client.get("/security/login-history", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 1
    
    def test_list_alerts(self, client, auth_header):
        response = client.get("/security/alerts", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)


class TestGetClientIP:
    """Tests for get_client_ip helper."""
    
    def test_direct_connection(self):
        mock_request = MagicMock()
        mock_request.remote_addr = "192.168.1.1"
        mock_request.headers = {}
        ip = get_client_ip(mock_request)
        assert ip == "192.168.1.1"
    
    def test_x_forwarded_for(self):
        mock_request = MagicMock()
        mock_request.remote_addr = "10.0.0.1"
        mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 70.41.3.18"}
        ip = get_client_ip(mock_request)
        assert ip == "203.0.113.1"
    
    def test_x_real_ip(self):
        mock_request = MagicMock()
        mock_request.remote_addr = "10.0.0.1"
        mock_request.headers = {"X-Real-IP": "198.51.100.1"}
        ip = get_client_ip(mock_request)
        assert ip == "198.51.100.1"
