"""Tests for device trust management (issue #125)."""

import pytest
from app.services.device_trust import record_login, get_devices, trust_device, revoke_device


def test_record_new_device(app_fixture):
    with app_fixture.app_context():
        device, is_new = record_login(1, "Mozilla/5.0 Chrome", "192.168.1.50")
        assert is_new is True
        assert device["login_count"] == 1
        assert device["trusted"] is False


def test_record_existing_device(app_fixture):
    with app_fixture.app_context():
        record_login(1, "Mozilla/5.0 Chrome", "192.168.1.50")
        device, is_new = record_login(1, "Mozilla/5.0 Chrome", "192.168.1.99")
        # Same IP prefix (192.168.1) + same UA = same device
        assert is_new is False
        assert device["login_count"] == 2


def test_different_ua_is_new_device(app_fixture):
    with app_fixture.app_context():
        record_login(1, "Mozilla/5.0 Chrome", "192.168.1.50")
        device, is_new = record_login(1, "Mozilla/5.0 Safari", "192.168.1.50")
        assert is_new is True


def test_list_devices(app_fixture):
    with app_fixture.app_context():
        record_login(1, "Chrome", "10.0.0.1")
        record_login(1, "Safari", "10.0.0.2")
        devices = get_devices(1)
        assert len(devices) == 2


def test_trust_and_revoke(app_fixture):
    with app_fixture.app_context():
        device, _ = record_login(1, "Chrome", "10.0.0.1")
        assert trust_device(1, device["device_id"]) is True

        devices = get_devices(1)
        trusted = [d for d in devices if d["trusted"]]
        assert len(trusted) == 1

        assert revoke_device(1, device["device_id"]) is True
        devices = get_devices(1)
        trusted = [d for d in devices if d["trusted"]]
        assert len(trusted) == 0


def test_api_list_devices(client, auth_header):
    resp = client.get("/devices", headers=auth_header)
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)
