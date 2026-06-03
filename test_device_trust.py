"""
Tests for device trust management and recognition.
"""
import pytest
from unittest.mock import patch
from app.models.device import (
    TrustedDevice,
    hash_fingerprint,
    hash_ip,
    is_trusted_device,
    register_device,
    trust_device,
)
from app.models import User
from app.extensions import db


class TestHashFunctions:
    """Test hash functions."""

    def test_hash_fingerprint_consistent(self):
        """Test that hash_fingerprint returns consistent results."""
        hash1 = hash_fingerprint("device123")
        hash2 = hash_fingerprint("device123")
        assert hash1 == hash2

    def test_hash_fingerprint_different_inputs(self):
        """Test that different inputs produce different hashes."""
        hash1 = hash_fingerprint("device123")
        hash2 = hash_fingerprint("device456")
        assert hash1 != hash2

    def test_hash_ip_consistent(self):
        """Test that hash_ip returns consistent results."""
        hash1 = hash_ip("192.168.1.1")
        hash2 = hash_ip("192.168.1.1")
        assert hash1 == hash2

    def test_hash_uses_pepper(self):
        """Test that hash uses PII_PEPPER."""
        with patch("app.models.device.PII_PEPPER", "test-pepper"):
            hash1 = hash_fingerprint("device123")
        
        with patch("app.models.device.PII_PEPPER", "different-pepper"):
            hash2 = hash_fingerprint("device123")
        
        assert hash1 != hash2


class TestRegisterDevice:
    """Test register_device function."""

    def test_register_new_device(self, app, db, sample_user):
        """Test registering a new device."""
        with app.app_context():
            device = register_device(
                user_id=sample_user.id,
                fingerprint="device123",
                name="My Phone",
                ip="192.168.1.1"
            )
            
            assert device.id is not None
            assert device.user_id == sample_user.id
            assert device.device_name == "My Phone"
            assert device.trusted is False  # Not trusted by default

    def test_register_existing_device_updates(self, app, db, sample_user):
        """Test that registering existing device updates it."""
        with app.app_context():
            # Register first time
            device1 = register_device(
                user_id=sample_user.id,
                fingerprint="device123",
                name="Old Name",
                ip="192.168.1.1"
            )
            
            # Register again with new name
            device2 = register_device(
                user_id=sample_user.id,
                fingerprint="device123",
                name="New Name",
                ip="192.168.1.2"
            )
            
            # Should be same device
            assert device1.id == device2.id
            assert device2.device_name == "New Name"
            
            # Should only have one device in DB
            count = TrustedDevice.query.filter_by(user_id=sample_user.id).count()
            assert count == 1

    def test_register_device_unique_constraint(self, app, db, sample_user):
        """Test unique constraint on user_id + fingerprint."""
        with app.app_context():
            register_device(user_id=sample_user.id, fingerprint="device123")
            register_device(user_id=sample_user.id, fingerprint="device456")
            
            count = TrustedDevice.query.filter_by(user_id=sample_user.id).count()
            assert count == 2


class TestIsTrustedDevice:
    """Test is_trusted_device function."""

    def test_trusted_device(self, app, db, sample_user):
        """Test checking trusted device."""
        with app.app_context():
            device = register_device(user_id=sample_user.id, fingerprint="device123")
            trust_device(user_id=sample_user.id, fingerprint="device123")
            
            assert is_trusted_device(user_id=sample_user.id, fingerprint="device123") is True

    def test_untrusted_device(self, app, db, sample_user):
        """Test checking untrusted device."""
        with app.app_context():
            register_device(user_id=sample_user.id, fingerprint="device123")
            
            assert is_trusted_device(user_id=sample_user.id, fingerprint="device123") is False

    def test_nonexistent_device(self, app, db, sample_user):
        """Test checking non-existent device."""
        with app.app_context():
            assert is_trusted_device(user_id=sample_user.id, fingerprint="nonexistent") is False

    def test_updates_last_seen(self, app, db, sample_user):
        """Test that checking trusted device updates last_seen."""
        with app.app_context():
            device = register_device(user_id=sample_user.id, fingerprint="device123")
            trust_device(user_id=sample_user.id, fingerprint="device123")
            
            old_last_seen = device.last_seen
            is_trusted_device(user_id=sample_user.id, fingerprint="device123")
            
            updated_device = TrustedDevice.query.get(device.id)
            assert updated_device.last_seen >= old_last_seen


class TestTrustDevice:
    """Test trust_device function."""

    def test_trust_existing_device(self, app, db, sample_user):
        """Test trusting an existing device."""
        with app.app_context():
            register_device(user_id=sample_user.id, fingerprint="device123")
            
            result = trust_device(user_id=sample_user.id, fingerprint="device123")
            
            assert result is True
            device = TrustedDevice.query.filter_by(
                user_id=sample_user.id,
                device_fingerprint_hash=hash_fingerprint("device123")
            ).first()
            assert device.trusted is True

    def test_trust_nonexistent_device(self, app, db, sample_user):
        """Test trusting a non-existent device."""
        with app.app_context():
            result = trust_device(user_id=sample_user.id, fingerprint="nonexistent")
            
            assert result is False


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
