def test_compute_fingerprint_unique():
    from app.services.device_trust import compute_fingerprint
    fp1 = compute_fingerprint(user_agent="Chrome/120", ip_address="192.168.1.1", accept_language="en-US")
    fp2 = compute_fingerprint(user_agent="Firefox/120", ip_address="192.168.1.1", accept_language="en-US")
    assert fp1 != fp2
    assert len(fp1) == 64

def test_register_device_creates_entry(app_fixture):
    from app.extensions import db
    from app.models import Device, User
    from app.services.device_trust import register_device
    with app_fixture.app_context():
        user = User(email="dev@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()
        d = register_device(user_id=user.id, user_agent="Chrome/1", ip_address="10.0.0.1", accept_language="en")
        assert d.id is not None

def test_list_devices_endpoint(client, auth_header):
    r = client.get("/auth/devices", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
