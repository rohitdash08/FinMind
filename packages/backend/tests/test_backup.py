"""Tests for encrypted backup (issue #126)."""
import pytest

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def _seed(db):
    from werkzeug.security import generate_password_hash
    from app.models import User
    u = User(email="backup@test.com", password_hash=generate_password_hash("pw"))
    db.session.add(u); db.session.commit()
    return u

def test_encrypt_decrypt_roundtrip():
    app = _app()
    with app.app_context():
        from app.extensions import db
        db.create_all(); u = _seed(db)
        from app.services.backup import create_encrypted_backup, decrypt_backup
        payload = create_encrypted_backup(u.id, "securepass123")
        assert isinstance(payload, bytes)
        assert len(payload) > 28
        data = decrypt_backup(payload, "securepass123")
        assert data["user_id"] == u.id
        assert data["email"] == "backup@test.com"

def test_wrong_password_fails():
    app = _app()
    with app.app_context():
        from app.extensions import db
        db.create_all(); u = _seed(db)
        from app.services.backup import create_encrypted_backup, decrypt_backup
        payload = create_encrypted_backup(u.id, "correctpass")
        with pytest.raises(Exception):  # cryptography raises InvalidTag
            decrypt_backup(payload, "wrongpass")

def test_plaintext_backup_is_zip():
    app = _app()
    with app.app_context():
        from app.extensions import db
        db.create_all(); u = _seed(db)
        from app.services.backup import create_plaintext_backup
        import zipfile, io
        data = create_plaintext_backup(u.id)
        assert zipfile.is_zipfile(io.BytesIO(data))

def test_different_passwords_produce_different_ciphertext():
    app = _app()
    with app.app_context():
        from app.extensions import db
        db.create_all(); u = _seed(db)
        from app.services.backup import create_encrypted_backup
        p1 = create_encrypted_backup(u.id, "pass1111")
        p2 = create_encrypted_backup(u.id, "pass2222")
        assert p1 != p2  # different salts + different keys
