"""
Tests for Device Trust Management

Covers:
- Trusting devices
- Removing device trust
- Listing trusted devices
- Checking device trust status
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import User, TrustedDevice
from app.services.login_anomaly import (
    get_trusted_devices,
    trust_device,
    remove_device_trust,
    is_device_trusted,
    update_device_last_used,
    get_device_by_id,
)


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


@pytest.fixture
def auth_header(client):
    """Register and login a user, return auth header."""
    email = "device@test.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


class TestTrustDevice:
    """Tests for trusting devices."""
    
    def test_trust_new_device(self, app, test_user):
        """Trust a new device."""
        with app.app_context():
            device = trust_device(
                user_id=test_user,
                device_fingerprint="abc123def456",
                device_name="My Laptop",
                user_agent="Mozilla/5.0",
                ip_address="192.168.1.1"
            )
            
            assert device.id is not None
            assert device.device_fingerprint == "abc123def456"
            assert device.device_name == "My Laptop"
            assert device.is_active is True
    
    def test_trust_existing_device_updates(self, app, test_user):
        """Trusting an existing device should update it."""
        with app.app_context():
            # Trust device first time
            device1 = trust_device(
                user_id=test_user,
                device_fingerprint="abc123",
                device_name="My Laptop"
            )
            
            # Trust same device again
            device2 = trust_device(
                user_id=test_user,
                device_fingerprint="abc123",
                device_name="Updated Name"
            )
            
            assert device1.id == device2.id
            assert device2.device_name == "Updated Name"
    
    def test_is_device_trusted(self, app, test_user):
        """Check if device is trusted."""
        with app.app_context():
            # Not trusted initially
            assert is_device_trusted(test_user, "abc123") is False
            
            # Trust the device
            trust_device(test_user, "abc123")
            
            # Now it should be trusted
            assert is_device_trusted(test_user, "abc123") is True


class TestRemoveDeviceTrust:
    """Tests for removing device trust."""
    
    def test_remove_device_trust(self, app, test_user):
        """Remove trust from a device."""
        with app.app_context():
            device = trust_device(
                user_id=test_user,
                device_fingerprint="abc123"
            )
            
            assert is_device_trusted(test_user, "abc123") is True
            
            success = remove_device_trust(test_user, device.id)
            
            assert success is True
            assert is_device_trusted(test_user, "abc123") is False
    
    def test_remove_nonexistent_device(self, app, test_user):
        """Removing nonexistent device should return False."""
        with app.app_context():
            success = remove_device_trust(test_user, 9999)
            assert success is False


class TestGetTrustedDevices:
    """Tests for listing trusted devices."""
    
    def test_get_trusted_devices_empty(self, app, test_user):
        """Get empty list when no trusted devices."""
        with app.app_context():
            devices = get_trusted_devices(test_user)
            assert len(devices) == 0
    
    def test_get_trusted_devices(self, app, test_user):
        """Get list of trusted devices."""
        with app.app_context():
            trust_device(test_user, "device1", device_name="Laptop")
            trust_device(test_user, "device2", device_name="Phone")
            
            devices = get_trusted_devices(test_user)
            
            assert len(devices) == 2
            names = [d["device_name"] for d in devices]
            assert "Laptop" in names
            assert "Phone" in names
    
    def test_removed_devices_not_listed(self, app, test_user):
        """Removed devices should not be in list."""
        with app.app_context():
            device = trust_device(test_user, "device1")
            trust_device(test_user, "device2")
            
            remove_device_trust(test_user, device.id)
            
            devices = get_trusted_devices(test_user)
            assert len(devices) == 1


class TestUpdateDevice:
    """Tests for updating device info."""
    
    def test_update_device_last_used(self, app, test_user):
        """Update last used timestamp."""
        with app.app_context():
            device = trust_device(test_user, "abc123")
            original_time = device.last_used_at
            
            update_device_last_used(test_user, "abc123")
            
            db.session.refresh(device)
            assert device.last_used_at >= original_time
    
    def test_get_device_by_id(self, app, test_user):
        """Get device by ID."""
        with app.app_context():
            device = trust_device(test_user, "abc123", device_name="Test Device")
            
            found = get_device_by_id(test_user, device.id)
            
            assert found is not None
            assert found.device_name == "Test Device"


class TestDeviceTrustAPI:
    """Tests for device trust API endpoints."""
    
    def test_list_devices_endpoint(self, client, auth_header):
        """Test GET /security/devices endpoint."""
        r = client.get("/security/devices", headers=auth_header)
        
        assert r.status_code == 200
        data = r.get_json()
        assert "devices" in data
        assert "count" in data
    
    def test_trust_device_endpoint(self, client, auth_header):
        """Test POST /security/devices/trust endpoint."""
        r = client.post(
            "/security/devices/trust",
            json={"device_name": "Test Device"},
            headers=auth_header
        )
        
        assert r.status_code == 201
        data = r.get_json()
        assert "device" in data
        assert data["device"]["device_name"] == "Test Device"
    
    def test_remove_trust_endpoint(self, client, auth_header):
        """Test DELETE /security/devices/:id endpoint."""
        # First trust a device
        r = client.post(
            "/security/devices/trust",
            json={"device_name": "To Remove"},
            headers=auth_header
        )
        device_id = r.get_json()["device"]["id"]
        
        # Then remove it
        r = client.delete(f"/security/devices/{device_id}", headers=auth_header)
        
        assert r.status_code == 200
    
    def test_device_status_endpoint(self, client, auth_header):
        """Test GET /security/devices/status endpoint."""
        r = client.get("/security/devices/status", headers=auth_header)
        
        assert r.status_code == 200
        data = r.get_json()
        assert "trusted" in data
    
    def test_update_device_endpoint(self, client, auth_header):
        """Test PATCH /security/devices/:id endpoint."""
        # First trust a device
        r = client.post(
            "/security/devices/trust",
            json={"device_name": "Old Name"},
            headers=auth_header
        )
        device_id = r.get_json()["device"]["id"]
        
        # Update the name
        r = client.patch(
            f"/security/devices/{device_id}",
            json={"device_name": "New Name"},
            headers=auth_header
        )
        
        assert r.status_code == 200
        assert r.get_json()["device"]["device_name"] == "New Name"
    
    def test_unauthorized_access(self, client):
        """Unauthorized requests should be rejected."""
        r = client.get("/security/devices")
        assert r.status_code == 401
        
        r = client.post("/security/devices/trust", json={})
        assert r.status_code == 401