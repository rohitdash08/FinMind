"""Tests for client-side encryption."""

import pytest
from app.services.encryption import (
    setup_encryption, verify_passphrase, encrypt_field, decrypt_field,
    list_fields, delete_field, rotate_key, has_encryption,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(identity=str(user))


@pytest.fixture
def encrypted_user(app, user):
    with app.app_context():
        setup_encryption(user, "mypassphrase")
        return user


PASS = "mypassphrase"


class TestSetup:
    def test_setup(self, app, user):
        with app.app_context():
            result = setup_encryption(user, PASS)
            assert result["status"] == "ok"
            assert has_encryption(user) is True

    def test_no_encryption(self, app, user):
        with app.app_context():
            assert has_encryption(user) is False

    def test_duplicate_setup(self, app, encrypted_user):
        with app.app_context():
            with pytest.raises(ValueError):
                setup_encryption(encrypted_user, PASS)


class TestVerify:
    def test_correct(self, app, encrypted_user):
        with app.app_context():
            assert verify_passphrase(encrypted_user, PASS) is True

    def test_wrong(self, app, encrypted_user):
        with app.app_context():
            assert verify_passphrase(encrypted_user, "wrong") is False

    def test_no_setup(self, app, user):
        with app.app_context():
            assert verify_passphrase(user, PASS) is False


class TestEncryptDecrypt:
    def test_roundtrip(self, app, encrypted_user):
        with app.app_context():
            encrypt_field(encrypted_user, PASS, "account_number", "1234567890")
            value = decrypt_field(encrypted_user, PASS, "account_number")
            assert value == "1234567890"

    def test_update(self, app, encrypted_user):
        with app.app_context():
            encrypt_field(encrypted_user, PASS, "ssn", "111-22-3333")
            encrypt_field(encrypted_user, PASS, "ssn", "444-55-6666")
            value = decrypt_field(encrypted_user, PASS, "ssn")
            assert value == "444-55-6666"

    def test_wrong_passphrase(self, app, encrypted_user):
        with app.app_context():
            with pytest.raises(ValueError):
                encrypt_field(encrypted_user, "wrong", "field", "value")

    def test_no_setup(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                encrypt_field(user, PASS, "field", "value")

    def test_field_not_found(self, app, encrypted_user):
        with app.app_context():
            with pytest.raises(ValueError):
                decrypt_field(encrypted_user, PASS, "nonexistent")


class TestFields:
    def test_list_empty(self, app, encrypted_user):
        with app.app_context():
            assert list_fields(encrypted_user) == []

    def test_list_with_data(self, app, encrypted_user):
        with app.app_context():
            encrypt_field(encrypted_user, PASS, "f1", "v1")
            encrypt_field(encrypted_user, PASS, "f2", "v2")
            fields = list_fields(encrypted_user)
            assert len(fields) == 2

    def test_delete(self, app, encrypted_user):
        with app.app_context():
            encrypt_field(encrypted_user, PASS, "f1", "v1")
            assert delete_field(encrypted_user, "f1") is True
            assert list_fields(encrypted_user) == []

    def test_delete_not_found(self, app, encrypted_user):
        with app.app_context():
            assert delete_field(encrypted_user, "nope") is False


class TestRotate:
    def test_rotate(self, app, encrypted_user):
        with app.app_context():
            encrypt_field(encrypted_user, PASS, "secret", "hello")
            result = rotate_key(encrypted_user, PASS, "newpass")
            assert result["fields_rotated"] == 1
            value = decrypt_field(encrypted_user, "newpass", "secret")
            assert value == "hello"

    def test_wrong_old(self, app, encrypted_user):
        with app.app_context():
            with pytest.raises(ValueError):
                rotate_key(encrypted_user, "wrong", "newpass")

    def test_no_setup(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                rotate_key(user, PASS, "newpass")


class TestAPI:
    def test_status(self, app, user, token):
        client = app.test_client()
        resp = client.get("/encryption/status", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["enabled"] is False

    def test_setup(self, app, user, token):
        client = app.test_client()
        resp = client.post("/encryption/setup", json={"passphrase": PASS},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_verify(self, app, encrypted_user, token):
        client = app.test_client()
        resp = client.post("/encryption/verify", json={"passphrase": PASS},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.get_json()["valid"] is True

    def test_encrypt(self, app, encrypted_user, token):
        client = app.test_client()
        resp = client.post("/encryption/encrypt",
                           json={"passphrase": PASS, "field_name": "test", "value": "secret"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_decrypt(self, app, encrypted_user, token):
        client = app.test_client()
        client.post("/encryption/encrypt",
                     json={"passphrase": PASS, "field_name": "test", "value": "secret"},
                     headers={"Authorization": f"Bearer {token}"})
        resp = client.post("/encryption/decrypt",
                           json={"passphrase": PASS, "field_name": "test"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.get_json()["value"] == "secret"

    def test_fields(self, app, encrypted_user, token):
        client = app.test_client()
        resp = client.get("/encryption/fields", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
