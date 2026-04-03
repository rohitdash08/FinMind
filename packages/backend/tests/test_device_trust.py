"""Tests for Device Trust Management & Recognition (issue #125)."""
import pytest
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash
from app.services.device_trust import (
    register_device,
    verify_device_token,
    revoke_device,
    revoke_all_devices,
    get_user_devices,
    recognize_device,
    TrustedDevice,
    _generate_device_token,
    _fingerprint_device,
)
from app.models import User
from app.extensions import db

try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url("redis://localhost:6379/15")
    _r.ping()
    _redis_available = True
except Exception:
    _redis_available = False

requires_redis = pytest.mark.skipif(
    not _redis_available, reason="Redis not available"
)


def _make_user(email="device@test.com"):
    user = User(
        email=email,
        password_hash=generate_password_hash("pass"),
        preferred_currency="USD",
    )
    db.session.add(user)
    db.session.flush()
    return user


# -----------------------------------------------------------------------
# Unit tests
# -----------------------------------------------------------------------

class TestHelpers:
    def test_generate_device_token_unique(self):
        t1 = _generate_device_token()
        t2 = _generate_device_token()
        assert t1 != t2
        assert len(t1) == 64

    def test_fingerprint_deterministic(self):
        f1 = _fingerprint_device("Mozilla/5.0", "192.168.1.1")
        f2 = _fingerprint_device("Mozilla/5.0", "192.168.1.1")
        assert f1 == f2
        assert len(f1) == 32

    def test_fingerprint_different_ua(self):
        f1 = _fingerprint_device("Chrome", "192.168.1.1")
        f2 = _fingerprint_device("Firefox", "192.168.1.1")
        assert f1 != f2

    def test_fingerprint_different_ip(self):
        f1 = _fingerprint_device("Chrome", "1.1.1.1")
        f2 = _fingerprint_device("Chrome", "2.2.2.2")
        assert f1 != f2


class TestTrustedDeviceModel:
    def test_not_expired_when_no_expiry(self):
        device = TrustedDevice(
            user_id=1,
            device_token="abc",
            device_name="Test",
            is_trusted=True,
        )
        assert device._is_expired() is False

    def test_expired_with_past_expiry(self):
        device = TrustedDevice(
            user_id=1,
            device_token="abc",
            device_name="Test",
            is_trusted=True,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        assert device._is_expired() is True

    def test_not_expired_with_future_expiry(self):
        device = TrustedDevice(
            user_id=1,
            device_token="abc",
            device_name="Test",
            is_trusted=True,
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        assert device._is_expired() is False


# -----------------------------------------------------------------------
# Integration tests
# -----------------------------------------------------------------------

class TestRegisterDevice:
    def test_register_creates_device(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("reg@test.com")
            db.session.commit()
            device = register_device(user.id, "My Laptop")
            assert device.id is not None
            assert device.user_id == user.id
            assert device.is_trusted is True
            assert len(device.device_token) == 64

    def test_register_with_expiry(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("expiry@test.com")
            db.session.commit()
            device = register_device(user.id, "Temp Device", trust_days=7)
            assert device.expires_at is not None
            delta = device.expires_at - datetime.utcnow()
            assert 6 <= delta.days <= 7

    def test_register_no_expiry(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("noexp@test.com")
            db.session.commit()
            device = register_device(user.id, "Permanent", trust_days=None)
            assert device.expires_at is None

    def test_register_with_fingerprint(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("fp@test.com")
            db.session.commit()
            device = register_device(
                user.id, "Browser",
                user_agent="Mozilla/5.0",
                ip_address="10.0.0.1",
            )
            assert device.device_fingerprint is not None


class TestVerifyDevice:
    def test_verify_valid_token(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("verify@test.com")
            db.session.commit()
            device = register_device(user.id, "Phone")
            result = verify_device_token(device.device_token, user_id=user.id)
            assert result is not None
            assert result.id == device.id

    def test_verify_wrong_token(self, app_fixture):
        with app_fixture.app_context():
            result = verify_device_token("invalidtoken")
            assert result is None

    def test_verify_expired_device(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("expdev@test.com")
            db.session.commit()
            device = register_device(user.id, "Old Device", trust_days=0)
            # Force expiry
            device.expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()
            result = verify_device_token(device.device_token, user_id=user.id)
            assert result is None

    def test_verify_wrong_user(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("owner@test.com")
            db.session.commit()
            device = register_device(user.id, "My Device")
            result = verify_device_token(device.device_token, user_id=999)
            assert result is None


class TestRevokeDevice:
    def test_revoke_device(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("revoke@test.com")
            db.session.commit()
            device = register_device(user.id, "Old Phone")
            result = revoke_device(device.id, user.id)
            assert result is not None
            assert result.is_trusted is False

    def test_revoke_wrong_user(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("rev2@test.com")
            db.session.commit()
            device = register_device(user.id, "Laptop")
            result = revoke_device(device.id, 999)
            assert result is None

    def test_revoke_all(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("revokeall@test.com")
            db.session.commit()
            d1 = register_device(user.id, "Device A")
            d2 = register_device(user.id, "Device B")
            d3 = register_device(user.id, "Device C")
            count = revoke_all_devices(user.id)
            assert count == 3
            devices = get_user_devices(user.id)
            assert len(devices) == 0

    def test_revoke_all_except_current(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("keepone@test.com")
            db.session.commit()
            d1 = register_device(user.id, "Current")
            d2 = register_device(user.id, "Other")
            count = revoke_all_devices(user.id, except_token=d1.device_token)
            assert count == 1
            devices = get_user_devices(user.id)
            assert len(devices) == 1
            assert devices[0]["device_name"] == "Current"


class TestRecognizeDevice:
    def test_recognize_by_fingerprint(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("recog@test.com")
            db.session.commit()
            device = register_device(
                user.id, "Home PC",
                user_agent="TestAgent/1.0",
                ip_address="192.168.0.1",
            )
            found = recognize_device(
                user.id,
                user_agent="TestAgent/1.0",
                ip_address="192.168.0.1",
            )
            assert found is not None
            assert found.id == device.id

    def test_recognize_wrong_fingerprint(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("recog2@test.com")
            db.session.commit()
            register_device(user.id, "Home", user_agent="Chrome", ip_address="1.1.1.1")
            found = recognize_device(user.id, user_agent="Firefox", ip_address="2.2.2.2")
            assert found is None


# -----------------------------------------------------------------------
# API tests (require Redis)
# -----------------------------------------------------------------------

@requires_redis
class TestDeviceTrustAPI:
    def test_list_devices_empty(self, client, auth_header):
        resp = client.get("/devices", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "devices" in data

    def test_add_device(self, client, auth_header):
        resp = client.post("/devices", json={"device_name": "My Laptop"}, headers=auth_header)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["device_name"] == "My Laptop"
        assert data["is_trusted"] is True
        assert "device_token" in data

    def test_add_device_no_name(self, client, auth_header):
        resp = client.post("/devices", json={}, headers=auth_header)
        assert resp.status_code == 400

    def test_verify_device_token(self, client, auth_header):
        create_resp = client.post("/devices", json={"device_name": "Phone"}, headers=auth_header)
        token = create_resp.get_json()["device_token"]
        resp = client.post("/devices/verify", json={"device_token": token}, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trusted"] is True

    def test_revoke_device(self, client, auth_header):
        create_resp = client.post("/devices", json={"device_name": "Tablet"}, headers=auth_header)
        device_id = create_resp.get_json()["id"]
        resp = client.delete(f"/devices/{device_id}", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["device"]["is_trusted"] is False

    def test_revoke_all(self, client, auth_header):
        client.post("/devices", json={"device_name": "D1"}, headers=auth_header)
        client.post("/devices", json={"device_name": "D2"}, headers=auth_header)
        resp = client.post("/devices/revoke-all", json={}, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["revoked_count"] >= 2