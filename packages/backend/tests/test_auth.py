def test_auth_refresh_flow(client):
    # Register user
    email = "refresh@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)  # 409 if already exists

    # Login to get tokens
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data and "refresh_token" in data

    # Use refresh to get a new access token
    refresh_token = data["refresh_token"]
    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200
    new_access = r.get_json().get("access_token")
    assert isinstance(new_access, str) and len(new_access) > 10


def test_auth_logout_revokes_refresh_token(client):
    email = "logout@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    refresh_token = r.get_json()["refresh_token"]

    r = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 401


from app.models import User, LoginAttempt # Import new models for assertions
import pytest # Required for mocker fixture

def test_auth_me_and_update_preferred_currency(client):
    email = "profile@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    me = r.get_json()
    assert me["email"] == email
    assert me["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "inr"}, headers=auth)
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "ZZZ"}, headers=auth)
    assert r.status_code == 400


def test_login_records_attempt_and_updates_last_login(client):
    email = "login_rec@test.com"
    password = "password123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login attempt
    initial_ip = "192.168.1.1"
    initial_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": initial_ua},
        environ_base={'REMOTE_ADDR': initial_ip} # Mock IP address
    )
    assert r.status_code == 200
    user = User.query.filter_by(email=email).first()
    assert user.last_login_ip == initial_ip
    assert user.last_login_user_agent == initial_ua
    assert user.last_login_at is not None

    login_attempts = LoginAttempt.query.filter_by(user_id=user.id).all()
    assert len(login_attempts) == 1
    assert login_attempts[0].ip_address == initial_ip
    assert login_attempts[0].user_agent == initial_ua
    assert login_attempts[0].status == 'success'
    assert not login_attempts[0].is_suspicious


def test_failed_login_records_attempt(client):
    email = "failed_login@test.com"
    password = "password123"
    client.post("/auth/register", json={"email": email, "password": password})

    # Failed login attempt
    bad_ip = "1.2.3.4"
    bad_ua = "BadBrowser/1.0"
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong_password"},
        headers={"User-Agent": bad_ua},
        environ_base={'REMOTE_ADDR': bad_ip}
    )
    assert r.status_code == 401
    user = User.query.filter_by(email=email).first()
    
    # Last login details should NOT be updated for failed attempts
    # For a newly registered user, these would still be None
    assert user.last_login_ip is None 
    assert user.last_login_user_agent is None
    assert user.last_login_at is None

    login_attempts = LoginAttempt.query.filter_by(user_id=user.id).all()
    assert len(login_attempts) == 1
    assert login_attempts[0].ip_address == bad_ip
    assert login_attempts[0].user_agent == bad_ua
    assert login_attempts[0].status == 'failure'
    assert not login_attempts[0].is_suspicious


def test_suspicious_login_triggers_alert(client, mocker):
    email = "suspicious@test.com"
    password = "password123"
    client.post("/auth/register", json={"email": email, "password": password})

    # Mock the send_email function to verify it's called
    mock_send_email = mocker.patch('app.utils.email.send_email')

    # First successful login
    ip1 = "192.168.1.1"
    ua1 = "Mozilla/5.0 (Windows NT 10.0) Chrome/90.0"
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": ua1},
        environ_base={'REMOTE_ADDR': ip1}
    )
    user = User.query.filter_by(email=email).first()
    assert user.last_login_ip == ip1
    assert user.last_login_user_agent == ua1
    assert not mock_send_email.called # No alert for first login

    # Second login from different IP and User-Agent - should be suspicious
    ip2 = "10.0.0.5"
    ua2 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Firefox/89.0"
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": ua2},
        environ_base={'REMOTE_ADDR': ip2}
    )
    assert r.status_code == 200

    user = User.query.filter_by(email=email).first()
    assert user.last_login_ip == ip2
    assert user.last_login_user_agent == ua2

    login_attempts = LoginAttempt.query.filter_by(user_id=user.id).order_by(LoginAttempt.timestamp.desc()).all()
    assert len(login_attempts) == 2
    assert login_attempts[0].ip_address == ip2
    assert login_attempts[0].user_agent == ua2
    assert login_attempts[0].status == 'success'
    assert login_attempts[0].is_suspicious # This login should be marked suspicious

    assert mock_send_email.called # An alert should have been sent
    assert "Security Alert: Unusual Login Activity Detected!" in mock_send_email.call_args[0][1]
    assert f"IP Address: {ip2}" in mock_send_email.call_args[0][2]


def test_non_suspicious_login_does_not_trigger_alert(client, mocker):
    email = "non_suspicious@test.com"
    password = "password123"
    client.post("/auth/register", json={"email": email, "password": password})

    mock_send_email = mocker.patch('app.utils.email.send_email')

    # First successful login
    ip1 = "203.0.113.1"
    ua1 = "Mozilla/5.0 (Linux; Android 10) Chrome/88.0"
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": ua1},
        environ_base={'REMOTE_ADDR': ip1}
    )
    assert not mock_send_email.called

    # Second login from same IP and User-Agent - should not be suspicious
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": ua1},
        environ_base={'REMOTE_ADDR': ip1}
    )
    assert not mock_send_email.called

    user = User.query.filter_by(email=email).first()
    login_attempts = LoginAttempt.query.filter_by(user_id=user.id).all()
    assert len(login_attempts) == 2
    assert not login_attempts[0].is_suspicious
    assert not login_attempts[1].is_suspicious

    # Third login from same IP, but slightly different User-Agent (e.g., minor version change) - still not suspicious
    ua_minor_change = "Mozilla/5.0 (Linux; Android 10) Chrome/88.0.4324.192"
    client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": ua_minor_change},
        environ_base={'REMOTE_ADDR': ip1}
    )
    assert not mock_send_email.called # Should not trigger alert because IP is same

    user = User.query.filter_by(email=email).first()
    login_attempts = LoginAttempt.query.filter_by(user_id=user.id).order_by(LoginAttempt.timestamp.desc()).all()
    assert len(login_attempts) == 3
    assert not login_attempts[0].is_suspicious # Last login should not be suspicious
