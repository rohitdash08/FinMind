import json
from app.services.backup import (
    _encrypt, _decrypt, _derive_key,
    _password_hash, _verify_password,
    _collect_user_data,
)


def _create_test_user(app):
    from app.extensions import db
    from app.models import User
    user = User(email="backup_test@example.com", password_hash="hash", preferred_currency="INR")
    db.session.add(user)
    db.session.commit()
    return user.id


def test_derive_key():
    key, salt = _derive_key("testpassword")
    assert len(key) == 32
    assert len(salt) == 16


def test_encrypt_decrypt_roundtrip():
    password = "secure-pass-123!"
    plaintext = json.dumps({"hello": "world", "amount": 42.5})
    result = _encrypt(plaintext, password)
    assert "ciphertext" in result
    assert "iv" in result
    assert "tag" in result
    assert "salt" in result
    assert result["algo"] == "aes-256-gcm"
    decrypted = _decrypt(result, password)
    assert json.loads(decrypted) == {"hello": "world", "amount": 42.5}


def test_encrypt_wrong_password_fails():
    password = "correct-password"
    wrong = "wrong-password"
    plaintext = json.dumps({"secret": "data"})
    result = _encrypt(plaintext, password)
    try:
        _decrypt(result, wrong)
        assert False, "Should have raised exception"
    except Exception:
        pass


def test_password_hash_verify():
    pw = "my-backup-password"
    h, salt = _password_hash(pw)
    assert len(h) == 64
    assert len(salt) == 32
    assert _verify_password(pw, h, salt) is True
    assert _verify_password("wrong", h, salt) is False


def test_collect_user_data(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        data = _collect_user_data(uid)
        assert "version" in data
        assert "user" in data
        assert data["user"]["email"] == "backup_test@example.com"
        assert "expenses" in data
        assert "bills" in data


def test_create_and_list_backup(app_fixture):
    from app.services.backup import create_backup, list_backups, get_backup, decrypt_backup, delete_backup
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        result = create_backup(uid, "test-password-123")
        assert result["export_type"] == "full"
        assert result["record_count"] >= 0
        assert result["size_bytes"] > 0
        assert result["id"] is not None

        backups = list_backups(uid)
        assert len(backups) >= 1

        fetched = get_backup(uid, result["id"])
        assert fetched is not None
        assert fetched["filename"] == result["filename"]

        data = decrypt_backup(uid, result["id"], "test-password-123")
        assert data is not None
        assert "user" in data

        assert get_backup(uid, 99999) is None

        assert decrypt_backup(uid, result["id"], "wrong-password") is None

        assert delete_backup(uid, result["id"]) is True
        assert get_backup(uid, result["id"]) is None
        assert delete_backup(uid, 99999) is False
