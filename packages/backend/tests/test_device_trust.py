"""Tests for device trust management and recognition."""

import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import TrustedDevice


CHROME_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
SAFARI_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"


# ═══════════════════════════════════════════════════════════════════
# Service unit tests
# ═══════════════════════════════════════════════════════════════════


class TestDeviceFingerprint:
    """Test generate_device_id and parse_user_agent."""

    def test_generate_device_id_deterministic(self, app_fixture):
        from app.services.device_trust import generate_device_id

        id1 = generate_device_id(CHROME_UA, "192.168.1.100")
        id2 = generate_device_id(CHROME_UA, "192.168.1.100")
        assert id1 == id2

    def test_different_agents_different_ids(self, app_fixture):
        from app.services.device_trust import generate_device_id

        id1 = generate_device_id(CHROME_UA, "192.168.1.100")
        id2 = generate_device_id(FIREFOX_UA, "192.168.1.100")
        assert id1 != id2

    def test_same_ip_prefix_same_id(self, app_fixture):
        from app.services.device_trust import generate_device_id

        # Last octet changes don't affect fingerprint
        id1 = generate_device_id(CHROME_UA, "192.168.1.100")
        id2 = generate_device_id(CHROME_UA, "192.168.1.200")
        assert id1 == id2

    def test_device_id_length(self, app_fixture):
        from app.services.device_trust import generate_device_id

        did = generate_device_id(CHROME_UA, "10.0.0.1")
        assert len(did) == 32

    def test_parse_chrome_desktop(self, app_fixture):
        from app.services.device_trust import parse_user_agent

        info = parse_user_agent(CHROME_UA)
        assert info["device_type"] == "desktop"
        assert info["browser"] == "Chrome"
        assert info["os"] == "macOS"

    def test_parse_firefox_windows(self, app_fixture):
        from app.services.device_trust import parse_user_agent

        info = parse_user_agent(FIREFOX_UA)
        assert info["device_type"] == "desktop"
        assert info["browser"] == "Firefox"
        assert info["os"] == "Windows"

    def test_parse_safari_iphone(self, app_fixture):
        from app.services.device_trust import parse_user_agent

        info = parse_user_agent(SAFARI_UA)
        assert info["device_type"] == "mobile"
        assert info["browser"] == "Safari"
        assert info["os"] == "iOS"

    def test_parse_android(self, app_fixture):
        from app.services.device_trust import parse_user_agent

        info = parse_user_agent(ANDROID_UA)
        assert info["device_type"] == "mobile"
        assert info["browser"] == "Chrome"
        assert info["os"] == "Android"

    def test_parse_empty_ua(self, app_fixture):
        from app.services.device_trust import parse_user_agent

        info = parse_user_agent("")
        assert info["device_type"] == "desktop"
        assert info["browser"] == "Unknown"
        assert info["os"] == "Unknown"


class TestRegisterDevice:
    """Test register_device service function."""

    def test_register_new_device(self, client, auth_header):
        from app.services.device_trust import register_device

        with client.application.app_context():
            result = register_device(1, CHROME_UA, "192.168.1.100")

        assert result["device_type"] == "desktop"
        assert result["browser"] == "Chrome"
        assert result["os"] == "macOS"
        assert result["is_current"] is True
        assert result["trust_level"] == "standard"

    def test_register_with_custom_name(self, client, auth_header):
        from app.services.device_trust import register_device

        with client.application.app_context():
            result = register_device(1, CHROME_UA, "10.0.0.1",
                                     device_name="My MacBook")

        assert result["device_name"] == "My MacBook"

    def test_register_same_device_updates(self, client, auth_header):
        from app.services.device_trust import register_device

        with client.application.app_context():
            r1 = register_device(1, CHROME_UA, "192.168.1.100")
            r2 = register_device(1, CHROME_UA, "192.168.1.100",
                                 device_name="Updated Name")

        assert r1["id"] == r2["id"]  # Same record
        assert r2["device_name"] == "Updated Name"

    def test_register_resets_current_flag(self, client, auth_header):
        from app.services.device_trust import register_device, get_user_devices

        with client.application.app_context():
            register_device(1, CHROME_UA, "10.0.0.1")
            register_device(1, FIREFOX_UA, "10.0.0.2")

            devices = get_user_devices(1)
            current = [d for d in devices if d["is_current"]]
            assert len(current) == 1
            assert current[0]["browser"] == "Firefox"

    def test_register_with_full_trust(self, client, auth_header):
        from app.services.device_trust import register_device

        with client.application.app_context():
            result = register_device(1, CHROME_UA, "10.0.0.1",
                                     trust_level="full")

        assert result["trust_level"] == "full"

    def test_register_no_expiry(self, client, auth_header):
        from app.services.device_trust import register_device

        with client.application.app_context():
            result = register_device(1, CHROME_UA, "10.0.0.1",
                                     expires_days=0)

        assert result["expires_at"] is None


class TestRecognizeDevice:
    """Test recognize_device service function."""

    def test_recognize_known_device(self, client, auth_header):
        from app.services.device_trust import register_device, recognize_device

        with client.application.app_context():
            register_device(1, CHROME_UA, "192.168.1.100")
            result = recognize_device(1, CHROME_UA, "192.168.1.100")

        assert result["recognized"] is True
        assert result["trust_level"] == "standard"

    def test_unrecognized_device(self, client, auth_header):
        from app.services.device_trust import recognize_device

        with client.application.app_context():
            result = recognize_device(1, CHROME_UA, "10.0.0.1")

        assert result["recognized"] is False
        assert result["reason"] == "unknown_device"

    def test_revoked_device_not_recognized(self, client, auth_header):
        from app.services.device_trust import register_device, revoke_device, recognize_device

        with client.application.app_context():
            reg = register_device(1, CHROME_UA, "10.0.0.1")
            revoke_device(1, reg["id"])
            result = recognize_device(1, CHROME_UA, "10.0.0.1")

        assert result["recognized"] is False
        assert result["reason"] == "device_revoked"

    def test_expired_device_not_recognized(self, client, auth_header):
        from app.services.device_trust import register_device, recognize_device

        with client.application.app_context():
            reg = register_device(1, CHROME_UA, "10.0.0.1", expires_days=1)
            # Manually expire
            device = TrustedDevice.query.get(reg["id"])
            device.expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()

            result = recognize_device(1, CHROME_UA, "10.0.0.1")

        assert result["recognized"] is False
        assert result["reason"] == "trust_expired"


class TestDeviceManagement:
    """Test device listing, update, revoke, delete."""

    def test_list_devices(self, client, auth_header):
        from app.services.device_trust import register_device, get_user_devices

        with client.application.app_context():
            register_device(1, CHROME_UA, "10.0.0.1")
            register_device(1, FIREFOX_UA, "10.0.0.2")
            devices = get_user_devices(1)

        assert len(devices) == 2

    def test_list_excludes_revoked(self, client, auth_header):
        from app.services.device_trust import register_device, revoke_device, get_user_devices

        with client.application.app_context():
            r1 = register_device(1, CHROME_UA, "10.0.0.1")
            register_device(1, FIREFOX_UA, "10.0.0.2")
            revoke_device(1, r1["id"])
            devices = get_user_devices(1, include_revoked=False)

        assert len(devices) == 1

    def test_list_includes_revoked(self, client, auth_header):
        from app.services.device_trust import register_device, revoke_device, get_user_devices

        with client.application.app_context():
            r1 = register_device(1, CHROME_UA, "10.0.0.1")
            register_device(1, FIREFOX_UA, "10.0.0.2")
            revoke_device(1, r1["id"])
            devices = get_user_devices(1, include_revoked=True)

        assert len(devices) == 2

    def test_update_device_name(self, client, auth_header):
        from app.services.device_trust import register_device, update_device

        with client.application.app_context():
            reg = register_device(1, CHROME_UA, "10.0.0.1")
            result = update_device(1, reg["id"], device_name="Work PC")

        assert result["device_name"] == "Work PC"

    def test_update_trust_level(self, client, auth_header):
        from app.services.device_trust import register_device, update_device

        with client.application.app_context():
            reg = register_device(1, CHROME_UA, "10.0.0.1")
            result = update_device(1, reg["id"], trust_level="full")

        assert result["trust_level"] == "full"

    def test_update_invalid_trust(self, client, auth_header):
        from app.services.device_trust import register_device, update_device

        with client.application.app_context():
            reg = register_device(1, CHROME_UA, "10.0.0.1")
            result = update_device(1, reg["id"], trust_level="invalid")

        assert result is None

    def test_update_nonexistent(self, client, auth_header):
        from app.services.device_trust import update_device

        with client.application.app_context():
            result = update_device(1, 9999, device_name="test")

        assert result is None

    def test_revoke_device(self, client, auth_header):
        from app.services.device_trust import register_device, revoke_device

        with client.application.app_context():
            reg = register_device(1, CHROME_UA, "10.0.0.1")
            result = revoke_device(1, reg["id"])

        assert result is True

    def test_revoke_nonexistent(self, client, auth_header):
        from app.services.device_trust import revoke_device

        with client.application.app_context():
            assert revoke_device(1, 9999) is False

    def test_revoke_all_except_current(self, client, auth_header):
        from app.services.device_trust import register_device, revoke_all_devices, get_user_devices

        with client.application.app_context():
            register_device(1, CHROME_UA, "10.0.0.1")
            register_device(1, FIREFOX_UA, "10.0.0.2")  # This becomes current
            count = revoke_all_devices(1, except_current=True)

        assert count == 1

    def test_revoke_all_including_current(self, client, auth_header):
        from app.services.device_trust import register_device, revoke_all_devices, get_user_devices

        with client.application.app_context():
            register_device(1, CHROME_UA, "10.0.0.1")
            register_device(1, FIREFOX_UA, "10.0.0.2")
            count = revoke_all_devices(1, except_current=False)

        assert count == 2

    def test_delete_device(self, client, auth_header):
        from app.services.device_trust import register_device, delete_device, get_user_devices

        with client.application.app_context():
            reg = register_device(1, CHROME_UA, "10.0.0.1")
            assert delete_device(1, reg["id"]) is True
            assert get_user_devices(1) == []

    def test_delete_nonexistent(self, client, auth_header):
        from app.services.device_trust import delete_device

        with client.application.app_context():
            assert delete_device(1, 9999) is False


class TestDeviceStats:
    """Test get_device_stats."""

    def test_empty_stats(self, client, auth_header):
        from app.services.device_trust import get_device_stats

        with client.application.app_context():
            stats = get_device_stats(1)

        assert stats["total"] == 0
        assert stats["active"] == 0

    def test_stats_with_devices(self, client, auth_header):
        from app.services.device_trust import register_device, revoke_device, get_device_stats

        with client.application.app_context():
            r1 = register_device(1, CHROME_UA, "10.0.0.1")
            register_device(1, FIREFOX_UA, "10.0.0.2")
            register_device(1, SAFARI_UA, "10.0.0.3")
            revoke_device(1, r1["id"])

            stats = get_device_stats(1)

        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["revoked"] == 1
        assert "desktop" in stats["by_type"]
        assert "mobile" in stats["by_type"]


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestDeviceTrustRoutes:
    """Integration tests for /devices/* endpoints."""

    # ── POST /devices/register ──
    def test_register_device_route(self, client, auth_header):
        r = client.post("/devices/register", json={},
                        headers={**auth_header, "User-Agent": CHROME_UA})
        assert r.status_code == 201
        body = r.get_json()
        assert body["is_current"] is True
        assert body["trust_level"] == "standard"

    def test_register_with_name(self, client, auth_header):
        r = client.post("/devices/register",
                        json={"device_name": "My Laptop"},
                        headers={**auth_header, "User-Agent": CHROME_UA})
        assert r.status_code == 201
        assert r.get_json()["device_name"] == "My Laptop"

    def test_register_unauthorized(self, client):
        r = client.post("/devices/register", json={})
        assert r.status_code == 401

    # ── POST /devices/recognize ──
    def test_recognize_known(self, client, auth_header):
        client.post("/devices/register", json={},
                    headers={**auth_header, "User-Agent": CHROME_UA})
        r = client.post("/devices/recognize", json={},
                        headers={**auth_header, "User-Agent": CHROME_UA})
        assert r.status_code == 200
        assert r.get_json()["recognized"] is True

    def test_recognize_unknown(self, client, auth_header):
        r = client.post("/devices/recognize", json={},
                        headers={**auth_header, "User-Agent": FIREFOX_UA})
        assert r.status_code == 404
        assert r.get_json()["recognized"] is False

    # ── GET /devices/devices ──
    def test_list_devices_empty(self, client, auth_header):
        r = client.get("/devices/devices", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 0

    def test_list_devices_with_data(self, client, auth_header):
        client.post("/devices/register", json={},
                    headers={**auth_header, "User-Agent": CHROME_UA})
        client.post("/devices/register", json={},
                    headers={**auth_header, "User-Agent": FIREFOX_UA})
        r = client.get("/devices/devices", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 2

    def test_list_with_revoked(self, client, auth_header):
        cr = client.post("/devices/register", json={},
                         headers={**auth_header, "User-Agent": CHROME_UA})
        did = cr.get_json()["id"]
        client.post(f"/devices/devices/{did}/revoke", json={}, headers=auth_header)

        r = client.get("/devices/devices?include_revoked=true", headers=auth_header)
        assert r.get_json()["count"] == 1

        r2 = client.get("/devices/devices", headers=auth_header)
        assert r2.get_json()["count"] == 0

    # ── PATCH /devices/devices/<id> ──
    def test_update_device_route(self, client, auth_header):
        cr = client.post("/devices/register", json={},
                         headers={**auth_header, "User-Agent": CHROME_UA})
        did = cr.get_json()["id"]

        r = client.patch(f"/devices/devices/{did}",
                         json={"device_name": "Office PC", "trust_level": "full"},
                         headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["device_name"] == "Office PC"
        assert body["trust_level"] == "full"

    def test_update_nonexistent_route(self, client, auth_header):
        r = client.patch("/devices/devices/9999",
                         json={"device_name": "test"},
                         headers=auth_header)
        assert r.status_code == 404

    # ── POST /devices/devices/<id>/revoke ──
    def test_revoke_device_route(self, client, auth_header):
        cr = client.post("/devices/register", json={},
                         headers={**auth_header, "User-Agent": CHROME_UA})
        did = cr.get_json()["id"]

        r = client.post(f"/devices/devices/{did}/revoke", json={},
                        headers=auth_header)
        assert r.status_code == 200
        assert "revoked" in r.get_json()["message"]

    def test_revoke_nonexistent_route(self, client, auth_header):
        r = client.post("/devices/devices/9999/revoke", json={},
                        headers=auth_header)
        assert r.status_code == 404

    # ── POST /devices/devices/revoke-all ──
    def test_revoke_all_route(self, client, auth_header):
        client.post("/devices/register", json={},
                    headers={**auth_header, "User-Agent": CHROME_UA})
        client.post("/devices/register", json={},
                    headers={**auth_header, "User-Agent": FIREFOX_UA})

        r = client.post("/devices/devices/revoke-all", json={},
                        headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] >= 1

    # ── DELETE /devices/devices/<id> ──
    def test_delete_device_route(self, client, auth_header):
        cr = client.post("/devices/register", json={},
                         headers={**auth_header, "User-Agent": CHROME_UA})
        did = cr.get_json()["id"]

        r = client.delete(f"/devices/devices/{did}", headers=auth_header)
        assert r.status_code == 200
        assert "deleted" in r.get_json()["message"]

    def test_delete_nonexistent_route(self, client, auth_header):
        r = client.delete("/devices/devices/9999", headers=auth_header)
        assert r.status_code == 404

    def test_delete_unauthorized(self, client):
        r = client.delete("/devices/devices/1")
        assert r.status_code == 401

    # ── GET /devices/stats ──
    def test_stats_route(self, client, auth_header):
        client.post("/devices/register", json={},
                    headers={**auth_header, "User-Agent": CHROME_UA})
        r = client.get("/devices/stats", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["total"] == 1
        assert body["active"] == 1
