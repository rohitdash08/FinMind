"""Tests for device trust management (issue #125)."""
import pytest
from unittest.mock import MagicMock, patch
from app.extensions import db as _db
from app.models import User, TrustedDevice
from app.services.device_trust import fingerprint, record_login, device_to_dict


# ---------------------------------------------------------------------------
# Module-level autouse fixture: stub out redis so login doesn't need a real Redis
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Prevent all tests from requiring a live Redis instance."""
    import app.extensions as ext
    fake = MagicMock()
    fake.get.return_value = "uid"       # non-None → refresh token is valid
    fake.setex.return_value = True
    fake.delete.return_value = 1
    fake.flushdb.return_value = True
    monkeypatch.setattr(ext, "redis_client", fake)
    # Also patch the reference inside the auth route module
    import app.routes.auth as auth_mod
    monkeypatch.setattr(auth_mod, "redis_client", fake)
    return fake


# ---------------------------------------------------------------------------
# Fingerprint unit tests
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_deterministic(self):
        fp1 = fingerprint("Mozilla/5.0", "192.168.1.1")
        fp2 = fingerprint("Mozilla/5.0", "192.168.1.1")
        assert fp1 == fp2

    def test_different_agents_different_fp(self):
        assert fingerprint("Chrome", "1.1.1.1") != fingerprint("Firefox", "1.1.1.1")

    def test_different_ip_different_fp(self):
        assert fingerprint("Chrome", "1.1.1.1") != fingerprint("Chrome", "2.2.2.2")

    def test_returns_64_char_hex(self):
        fp = fingerprint("agent", "ip")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_none_values_handled(self):
        fp = fingerprint(None, None)
        assert isinstance(fp, str) and len(fp) == 64


# ---------------------------------------------------------------------------
# record_login service tests
# ---------------------------------------------------------------------------

class TestRecordLogin:
    def test_new_device_created(self, app_fixture):
        with app_fixture.app_context():
            user = User(email="d@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.commit()
            result = record_login(user.id, "Chrome/100", "1.2.3.4", _db.session)
            assert result["is_new"] is True
            assert result["trusted"] is False
            assert result["device_id"] is not None

    def test_known_device_not_duplicated(self, app_fixture):
        with app_fixture.app_context():
            user = User(email="d2@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.commit()
            record_login(user.id, "Chrome/100", "1.2.3.4", _db.session)
            record_login(user.id, "Chrome/100", "1.2.3.4", _db.session)
            count = _db.session.query(TrustedDevice).filter_by(user_id=user.id).count()
            assert count == 1

    def test_second_login_returns_is_new_false(self, app_fixture):
        with app_fixture.app_context():
            user = User(email="d3@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.commit()
            record_login(user.id, "Chrome/100", "1.2.3.4", _db.session)
            result = record_login(user.id, "Chrome/100", "1.2.3.4", _db.session)
            assert result["is_new"] is False

    def test_different_agents_create_separate_devices(self, app_fixture):
        with app_fixture.app_context():
            user = User(email="d4@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.commit()
            record_login(user.id, "Chrome/100",  "1.2.3.4", _db.session)
            record_login(user.id, "Firefox/100", "1.2.3.4", _db.session)
            count = _db.session.query(TrustedDevice).filter_by(user_id=user.id).count()
            assert count == 2

    def test_device_to_dict_truncates_fingerprint(self, app_fixture):
        with app_fixture.app_context():
            user = User(email="dt@x.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.flush()
            result = record_login(user.id, "Safari", "10.0.0.1", _db.session)
            device = _db.session.get(TrustedDevice, result["device_id"])
            d = device_to_dict(device)
            assert d["device_fingerprint"].endswith("...")
            assert len(d["device_fingerprint"]) < 64


# ---------------------------------------------------------------------------
# Device API endpoint tests
# ---------------------------------------------------------------------------

class TestDeviceAPI:
    def test_list_requires_auth(self, client):
        resp = client.get("/devices")
        assert resp.status_code in (401, 422)

    def test_trust_requires_auth(self, client):
        resp = client.post("/devices/1/trust")
        assert resp.status_code in (401, 422)

    def test_revoke_requires_auth(self, client):
        resp = client.post("/devices/1/revoke")
        assert resp.status_code in (401, 422)

    def test_forget_requires_auth(self, client):
        resp = client.delete("/devices/1")
        assert resp.status_code in (401, 422)

    def test_list_endpoint_exists(self, client):
        # Must not be 404 — should return auth error instead
        assert client.get("/devices").status_code != 404

    def test_list_devices_authenticated(self, client, auth_header):
        resp = client.get("/devices", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_login_records_device(self, client, auth_header):
        """Login should auto-record device; list should contain at least one entry."""
        resp = client.get("/devices", headers=auth_header)
        assert resp.status_code == 200
        devices = resp.get_json()
        # At least the device from the auth_header login should exist
        assert len(devices) >= 1

    def test_login_response_has_new_device_field(self, client):
        client.post("/auth/register", json={"email": "nd@x.com", "password": "pass1234"})
        resp = client.post("/auth/login", json={"email": "nd@x.com", "password": "pass1234"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "new_device" in body

    def test_trust_and_revoke_device(self, client, auth_header, app_fixture):
        """Trust then revoke a device."""
        with app_fixture.app_context():
            # Get the uid from auth_header login
            me = client.get("/auth/me", headers=auth_header)
            uid = me.get_json()["id"]
            device = (
                _db.session.query(TrustedDevice)
                .filter_by(user_id=uid)
                .first()
            )
            assert device is not None
            device_id = device.id

        resp = client.post(f"/devices/{device_id}/trust", headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json()["trusted"] is True

        resp = client.post(f"/devices/{device_id}/revoke", headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json()["trusted"] is False

    def test_forget_device(self, client, auth_header, app_fixture):
        """Delete a device removes it from the list."""
        with app_fixture.app_context():
            me = client.get("/auth/me", headers=auth_header)
            uid = me.get_json()["id"]
            device = (
                _db.session.query(TrustedDevice)
                .filter_by(user_id=uid)
                .first()
            )
            device_id = device.id

        resp = client.delete(f"/devices/{device_id}", headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "device forgotten"

        # Should now be gone from list
        resp = client.get("/devices", headers=auth_header)
        ids = [d["id"] for d in resp.get_json()]
        assert device_id not in ids

    def test_cannot_access_other_users_device(self, client, auth_header, app_fixture):
        """A device owned by user A cannot be trusted/deleted by user B."""
        # Register a second user
        client.post("/auth/register", json={"email": "b@x.com", "password": "pass5678"})
        r2 = client.post("/auth/login", json={"email": "b@x.com", "password": "pass5678"})
        token2 = r2.get_json()["access_token"]
        header2 = {"Authorization": f"Bearer {token2}"}

        # Get device_id belonging to user 1
        with app_fixture.app_context():
            me = client.get("/auth/me", headers=auth_header)
            uid = me.get_json()["id"]
            device = (
                _db.session.query(TrustedDevice)
                .filter_by(user_id=uid)
                .first()
            )
            if device is None:
                pytest.skip("No device available for ownership test")
            device_id = device.id

        resp = client.post(f"/devices/{device_id}/trust", headers=header2)
        assert resp.status_code == 404

    def test_set_device_name(self, client, auth_header, app_fixture):
        """PATCH /devices/<id>/name sets a friendly name."""
        with app_fixture.app_context():
            me = client.get("/auth/me", headers=auth_header)
            uid = me.get_json()["id"]
            device = (
                _db.session.query(TrustedDevice)
                .filter_by(user_id=uid)
                .first()
            )
            if device is None:
                pytest.skip("No device available for name test")
            device_id = device.id

        resp = client.patch(
            f"/devices/{device_id}/name",
            json={"name": "My Laptop"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.get_json()["device_name"] == "My Laptop"
