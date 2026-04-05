"""Tests for GDPR export & deletion (issue #76)."""
import zipfile, json, io, os, pytest


def _make_app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                       "AUDIT_LOG_DIR": "/tmp/test_audit"})


def _seed_user(db):
    from werkzeug.security import generate_password_hash
    from app.models import User
    u = User(email="test@gdpr.com", password_hash=generate_password_hash("pw"))
    db.session.add(u)
    db.session.commit()
    return u


def test_export_returns_zip():
    app = _make_app()
    with app.app_context():
        from app.extensions import db
        db.create_all()
        u = _seed_user(db)
        from app.services.gdpr import export_user_data
        data = export_user_data(u.id)
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        assert "profile.json" in names
        assert "expenses.json" in names
        assert "manifest.json" in names


def test_export_profile_contains_email():
    app = _make_app()
    with app.app_context():
        from app.extensions import db
        db.create_all()
        u = _seed_user(db)
        from app.services.gdpr import export_user_data
        data = export_user_data(u.id)
        zf = zipfile.ZipFile(io.BytesIO(data))
        profile = json.loads(zf.read("profile.json"))
        assert profile["email"] == "test@gdpr.com"


def test_delete_removes_user():
    app = _make_app()
    with app.app_context():
        from app.extensions import db
        db.create_all()
        u = _seed_user(db)
        uid = u.id
        from app.services.gdpr import delete_user_account
        from app.models import User
        result = delete_user_account(uid)
        assert db.session.get(User, uid) is None
        assert "deleted_at" in result


def test_delete_writes_audit_log():
    app = _make_app()
    with app.app_context():
        from app.extensions import db
        db.create_all()
        u = _seed_user(db)
        from app.services.gdpr import delete_user_account
        delete_user_account(u.id)
        log_path = "/tmp/test_audit/gdpr_audit.jsonl"
        assert os.path.exists(log_path)
        with open(log_path) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert any(e["action"] == "account_deleted" for e in lines)
