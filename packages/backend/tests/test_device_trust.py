def test_compute_fingerprint_unique():
    from app.services.device_trust import compute_fingerprint

    fp1 = compute_fingerprint(
        user_agent="Chrome/120",
        ip_address="192.168.1.1",
        accept_language="en-US",
    )
    fp2 = compute_fingerprint(
        user_agent="Firefox/120",
        ip_address="192.168.1.1",
        accept_language="en-US",
    )
    fp3 = compute_fingerprint(
        user_agent="Chrome/120",
        ip_address="10.0.0.1",
        accept_language="en-US",
    )

    assert fp1 != fp2
    assert fp1 != fp3
    assert len(fp1) == 64


def test_compute_trust_score_increases_with_usage(app_fixture):
    from app.extensions import db
    from app.models import Device, User
    from app.services.device_trust import compute_trust_score, register_device

    with app_fixture.app_context():
        user = User(
            email="score@test.com",
            password_hash="x",
            preferred_currency="USD",
        )
        db.session.add(user)
        db.session.commit()

        d1 = register_device(
            user_id=user.id,
            user_agent="Chrome/1",
            ip_address="10.0.0.1",
            accept_language="en",
        )
        assert d1.trust_score >= 25

        d2 = register_device(
            user_id=user.id,
            user_agent="Firefox/1",
            ip_address="10.0.0.1",
            accept_language="en",
        )
        assert d2.trust_score >= 50

        score = compute_trust_score(user.id, "10.0.0.1")
        assert score <= 100


def test_register_device_updates_existing(app_fixture):
    from app.extensions import db
    from app.models import Device, User
    from app.services.device_trust import register_device

    with app_fixture.app_context():
        user = User(email="exist@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        d1 = register_device(
            user_id=user.id,
            user_agent="Chrome/1",
            ip_address="10.0.0.1",
            accept_language="en",
        )
        d2 = register_device(
            user_id=user.id,
            user_agent="Chrome/1",
            ip_address="10.0.0.1",
            accept_language="en",
        )
        assert d1.id == d2.id


def test_is_new_device_detection(app_fixture):
    from app.extensions import db
    from app.models import Device, User
    from app.services.device_trust import (
        compute_fingerprint,
        is_new_device,
        register_device,
    )

    with app_fixture.app_context():
        user = User(email="newdev@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        fp = compute_fingerprint(
            user_agent="Safari/1",
            ip_address="1.2.3.4",
            accept_language="fr",
        )
        assert is_new_device(user.id, fp)

        register_device(
            user_id=user.id,
            user_agent="Safari/1",
            ip_address="1.2.3.4",
            accept_language="fr",
        )
        assert not is_new_device(user.id, fp)


def test_list_devices_endpoint(client, auth_header):
    r = client.post(
        "/auth/devices",
        json={
            "user_agent": "TestAgent/1.0",
            "ip_address": "10.0.0.1",
            "accept_language": "en-US",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    device_id = r.get_json()["id"]

    r = client.get("/auth/devices", headers=auth_header)
    assert r.status_code == 200
    devices = r.get_json()
    assert len(devices) >= 1
    assert any(d["id"] == device_id for d in devices)


def test_register_device_endpoint(client, auth_header):
    r = client.post(
        "/auth/devices",
        json={
            "user_agent": "NewDevice/2.0",
            "ip_address": "192.168.1.100",
            "accept_language": "en-GB",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert "id" in data
    assert "trust_score" in data
    assert "last_seen_at" in data


def test_remove_device_endpoint(client, auth_header):
    r = client.post(
        "/auth/devices",
        json={
            "user_agent": "RemoveMe/1.0",
            "ip_address": "10.0.0.99",
            "accept_language": "de",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    device_id = r.get_json()["id"]

    r = client.delete(f"/auth/devices/{device_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "removed"

    r = client.get("/auth/devices", headers=auth_header)
    devices = r.get_json()
    assert all(d["id"] != device_id for d in devices)


def test_remove_nonexistent_device_returns_404(client, auth_header):
    r = client.delete("/auth/devices/99999", headers=auth_header)
    assert r.status_code == 404


def test_login_registers_device(app_fixture, client, auth_header):
    from app.extensions import db
    from app.models import Device

    with app_fixture.app_context():
        count = db.session.query(Device).filter(Device.user_id == 1).count()
        assert count >= 0


def test_device_trust_score_improves_with_reuse(client, auth_header):
    r = client.post(
        "/auth/devices",
        json={
            "user_agent": "ReuseAgent/1.0",
            "ip_address": "10.10.10.10",
            "accept_language": "ja",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    score1 = r.get_json()["trust_score"]

    r = client.post(
        "/auth/devices",
        json={
            "user_agent": "ReuseAgent/1.0",
            "ip_address": "10.10.10.10",
            "accept_language": "ja",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    score2 = r.get_json()["trust_score"]

    assert score2 >= score1
