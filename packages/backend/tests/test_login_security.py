"""Tests for login anomaly detection."""
from app.routes.login_security import record_login

def test_requires_auth(client):
    assert client.get("/login-security/history").status_code in (401, 422)

def test_login_history(client, auth_header):
    r = client.get("/login-security/history", headers=auth_header)
    assert r.status_code == 200

def test_suspicious_endpoint(client, auth_header):
    r = client.get("/login-security/suspicious", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)

def test_login_stats(client, auth_header):
    r = client.get("/login-security/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "total_logins" in data
    assert "failed_attempts" in data
    assert "suspicious_events" in data

def test_record_login(app_fixture):
    with app_fixture.app_context():
        from app.extensions import db
        from app.models import User
        user = db.session.query(User).first()
        if not user:
            from werkzeug.security import generate_password_hash
            user = User(email="sec@test.com", password_hash=generate_password_hash("test"))
            db.session.add(user)
            db.session.commit()
        event = record_login(user.id, "1.2.3.4", "TestAgent", True)
        assert event.success is True
        assert event.suspicious is False

def test_new_ip_suspicious(app_fixture):
    with app_fixture.app_context():
        from app.extensions import db
        from app.models import User
        user = db.session.query(User).first()
        if not user:
            from werkzeug.security import generate_password_hash
            user = User(email="sec2@test.com", password_hash=generate_password_hash("test"))
            db.session.add(user)
            db.session.commit()
        record_login(user.id, "10.0.0.1", "Agent1", True)
        event2 = record_login(user.id, "99.99.99.99", "Agent2", True)
        assert event2.suspicious is True
        assert "New IP" in (event2.reason or "")
