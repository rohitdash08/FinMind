import pytest
from unittest.mock import patch
from flask import Flask
from app.models import User, UserDevice
from app.extensions import db


@patch("app.routes.auth.redis_client")
def test_login_anomaly_detection(mock_redis, client):
    # Mock redis to avoid connection errors
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True

    # Register and login for the first time
    email = "anomaly@example.com"
    password = "password123"
    client.post("/auth/register", json={"email": email, "password": password})
    
    # First login (from "device 1")
    r1 = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "Device1"}
    )
    assert r1.status_code == 200
    
    # Verify device 1 is stored
    with client.application.app_context():
        user = db.session.query(User).filter_by(email=email).first()
        devices = db.session.query(UserDevice).filter_by(user_id=user.id).all()
        assert len(devices) == 1
        assert devices[0].device_fingerprint is not None

    # Login from the same device (no new device should be created)
    r2 = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "Device1"}
    )
    assert r2.status_code == 200
    with client.application.app_context():
        devices = db.session.query(UserDevice).filter_by(user_id=user.id).all()
        assert len(devices) == 1

    # Login from a DIFFERENT device
    r3 = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "Device2"}
    )
    assert r3.status_code == 200
    with client.application.app_context():
        devices = db.session.query(UserDevice).filter_by(user_id=user.id).all()
        assert len(devices) == 2
        fingerprints = [d.device_fingerprint for d in devices]
        assert len(set(fingerprints)) == 2
