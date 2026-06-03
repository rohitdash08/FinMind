"""
Tests for login anomaly detection and suspicious activity alerts.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from app.services.anomaly import (
    LoginEvent,
    hash_ip,
    detect_anomaly,
)
from app.models import User
from app.extensions import db


class TestHashIp:
    """Test hash_ip function."""

    def test_consistent_hash(self):
        """Test that hash_ip returns consistent results."""
        hash1 = hash_ip("192.168.1.1")
        hash2 = hash_ip("192.168.1.1")
        assert hash1 == hash2

    def test_different_ips(self):
        """Test that different IPs produce different hashes."""
        hash1 = hash_ip("192.168.1.1")
        hash2 = hash_ip("10.0.0.1")
        assert hash1 != hash2


class TestDetectAnomaly:
    """Test detect_anomaly function."""

    def test_first_login_no_anomaly(self, app, db, sample_user):
        """Test first login is not flagged as anomaly."""
        with app.app_context():
            result = detect_anomaly(
                user_id=sample_user.id,
                ip="192.168.1.1",
                success=True
            )
            
            assert result["anomaly"] is False
            assert result["score"] == 0
            assert result["reasons"] == []

    def test_known_ip_no_anomaly(self, app, db, sample_user):
        """Test login from known IP is not anomaly."""
        with app.app_context():
            # First login
            detect_anomaly(user_id=sample_user.id, ip="192.168.1.1", success=True)
            
            # Second login from same IP
            result = detect_anomaly(
                user_id=sample_user.id,
                ip="192.168.1.1",
                success=True
            )
            
            assert result["anomaly"] is False

    def test_new_ip_flags_anomaly(self, app, db, sample_user):
        """Test login from new IP flags anomaly."""
        with app.app_context():
            # First login
            detect_anomaly(user_id=sample_user.id, ip="192.168.1.1", success=True)
            
            # Second login from different IP
            result = detect_anomaly(
                user_id=sample_user.id,
                ip="10.0.0.1",
                success=True
            )
            
            # New IP adds 0.3 to score
            assert result["new_ip"] is True
            assert result["score"] >= 0.3

    def test_rapid_attempts_flag_anomaly(self, app, db, sample_user):
        """Test rapid login attempts flag anomaly."""
        with app.app_context():
            # Create 6 logins in the last hour
            for i in range(6):
                event = LoginEvent(
                    user_id=sample_user.id,
                    ip_address_hash=hash_ip(f"192.168.1.{i}"),
                    success=True,
                    created_at=datetime.utcnow() - timedelta(minutes=i*5)
                )
                db.session.add(event)
            db.session.commit()
            
            # Now detect anomaly
            result = detect_anomaly(
                user_id=sample_user.id,
                ip="192.168.1.100",
                success=True
            )
            
            # Rapid attempts adds 0.5 to score
            assert result["rapid_attempts"] is True
            assert result["score"] >= 0.5

    def test_failed_logins_flag_anomaly(self, app, db, sample_user):
        """Test recent failed logins flag anomaly."""
        with app.app_context():
            # Create 4 failed logins in last 24 hours
            for i in range(4):
                event = LoginEvent(
                    user_id=sample_user.id,
                    ip_address_hash=hash_ip("192.168.1.1"),
                    success=False,
                    created_at=datetime.utcnow() - timedelta(hours=i*2)
                )
                db.session.add(event)
            db.session.commit()
            
            # Now detect anomaly
            result = detect_anomaly(
                user_id=sample_user.id,
                ip="192.168.1.1",
                success=True
            )
            
            # Failed logins adds 0.4 to score
            assert result["recent_failures"] == 4
            assert result["score"] >= 0.4

    def test_combined_anomaly(self, app, db, sample_user):
        """Test combination of anomaly signals."""
        with app.app_context():
            # First login
            detect_anomaly(user_id=sample_user.id, ip="192.168.1.1", success=True)
            
            # Create rapid attempts and failures
            for i in range(6):
                event = LoginEvent(
                    user_id=sample_user.id,
                    ip_address_hash=hash_ip(f"192.168.1.{i}"),
                    success=False,
                    created_at=datetime.utcnow() - timedelta(minutes=i*5)
                )
                db.session.add(event)
            db.session.commit()
            
            # Now detect anomaly with new IP
            result = detect_anomaly(
                user_id=sample_user.id,
                ip="10.0.0.1",
                success=True
            )
            
            # Should have all three signals
            assert result["new_ip"] is True
            assert result["rapid_attempts"] is True
            assert result["recent_failures"] > 3
            assert result["anomaly"] is True  # Score > 0.5 threshold

    def test_anomaly_threshold_configurable(self, app, db, sample_user):
        """Test that anomaly threshold is configurable."""
        with app.app_context():
            with patch("app.services.anomaly.os.environ", {"ANOMALY_THRESHOLD": "0.2"}):
                # First login
                detect_anomaly(user_id=sample_user.id, ip="192.168.1.1", success=True)
                
                # New IP (score = 0.3)
                result = detect_anomaly(
                    user_id=sample_user.id,
                    ip="10.0.0.1",
                    success=True
                )
                
                # With threshold 0.2, 0.3 should be anomaly
                assert result["anomaly"] is True


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app
    
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db(app):
    """Create database for testing."""
    with app.app_context():
        yield db


@pytest.fixture
def sample_user(app, db):
    """Create a sample user."""
    with app.app_context():
        user = User(email="test@example.com", currency="USD")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        return user
