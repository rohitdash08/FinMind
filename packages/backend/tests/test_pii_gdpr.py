"""Tests for PII Export & GDPR Account Deletion (issue #76)."""
import pytest
import json
import zipfile
import io
from werkzeug.security import generate_password_hash
from app.services.pii_gdpr import (
    export_user_pii,
    delete_user_pii,
    PIIExportPackage,
    DeletionAuditLog,
    _hash_email,
)
from app.models import User, Expense, Bill
from app.extensions import db
from datetime import date, datetime
from decimal import Decimal

try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url("redis://localhost:6379/15")
    _r.ping()
    _redis_available = True
except Exception:
    _redis_available = False

requires_redis = pytest.mark.skipif(
    not _redis_available, reason="Redis not available"
)


def _make_user(email="test@example.com", password="pass"):
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        preferred_currency="USD",
    )
    db.session.add(user)
    db.session.flush()
    return user


def _make_expense(user_id, amount="50.00"):
    from app.models import Expense
    from decimal import Decimal
    exp = Expense(
        user_id=user_id,
        amount=Decimal(amount),
        currency="USD",
        spent_at=date.today(),
    )
    db.session.add(exp)
    db.session.flush()
    return exp


# -----------------------------------------------------------------------
# Unit tests for PIIExportPackage
# -----------------------------------------------------------------------

class TestPIIExportPackage:
    def test_empty_package(self):
        pkg = PIIExportPackage(user_id=1)
        assert pkg.user_id == 1
        assert pkg.sections == {}

    def test_add_section(self):
        pkg = PIIExportPackage(user_id=1)
        pkg.add_section("expenses", [{"id": 1, "amount": "100"}])
        assert len(pkg.sections["expenses"]) == 1

    def test_to_dict(self):
        pkg = PIIExportPackage(user_id=42)
        pkg.add_section("profile", [{"id": 42, "email": "x@y.com"}])
        pkg.add_section("expenses", [{"id": 1}, {"id": 2}])
        d = pkg.to_dict()
        assert d["user_id"] == 42
        assert d["total_records"] == 3
        assert d["sections"]["profile"] == 1
        assert d["sections"]["expenses"] == 2

    def test_to_zip_bytes_valid_zip(self):
        pkg = PIIExportPackage(user_id=5)
        pkg.add_section("profile", [{"email": "a@b.com"}])
        zb = pkg.to_zip_bytes()
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            names = zf.namelist()
        assert "manifest.json" in names
        assert "profile.json" in names

    def test_zip_contains_manifest(self):
        pkg = PIIExportPackage(user_id=7)
        pkg.add_section("expenses", [{"id": 1}])
        zb = pkg.to_zip_bytes()
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["user_id"] == 7
        assert "expenses" in manifest["sections"]

    def test_checksum_deterministic(self):
        pkg = PIIExportPackage(user_id=3)
        pkg.add_section("profile", [{"id": 3}])
        c1 = pkg.checksum()
        c2 = pkg.checksum()
        assert c1 == c2
        assert len(c1) == 64  # SHA-256 hex

    def test_email_hash(self):
        h1 = _hash_email("User@Example.COM")
        h2 = _hash_email("user@example.com")
        assert h1 == h2  # case-insensitive
        assert len(h1) == 64


# -----------------------------------------------------------------------
# Integration tests (require app_fixture)
# -----------------------------------------------------------------------

class TestExportUserPii:
    def test_export_nonexistent_user(self, app_fixture):
        with app_fixture.app_context():
            pkg = export_user_pii(99999)
            assert pkg is None

    def test_export_returns_package(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("export@test.com")
            db.session.commit()
            pkg = export_user_pii(user.id)
            assert pkg is not None
            assert pkg.user_id == user.id

    def test_export_includes_profile(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("profile@test.com")
            db.session.commit()
            pkg = export_user_pii(user.id)
            profile_records = pkg.sections["profile"]
            assert len(profile_records) == 1
            assert profile_records[0]["email"] == "profile@test.com"

    def test_export_includes_expenses(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("expenses@test.com")
            _make_expense(user.id, "100.00")
            _make_expense(user.id, "200.00")
            db.session.commit()
            pkg = export_user_pii(user.id)
            assert len(pkg.sections["expenses"]) == 2

    def test_export_empty_sections_included(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("empty@test.com")
            db.session.commit()
            pkg = export_user_pii(user.id)
            # All sections present even if empty
            assert "expenses" in pkg.sections
            assert "bills" in pkg.sections
            assert "recurring_expenses" in pkg.sections


class TestDeleteUserPii:
    def test_delete_nonexistent_user(self, app_fixture):
        with app_fixture.app_context():
            result = delete_user_pii(99999)
            assert result is None

    def test_delete_removes_user(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("delete@test.com")
            user_id = user.id
            db.session.commit()
            result = delete_user_pii(user_id)
            assert result is not None
            assert result["status"] == "permanently_deleted"
            assert result["irreversible"] is True
            # Verify user is gone
            gone = User.query.filter_by(id=user_id).first()
            assert gone is None

    def test_delete_removes_expenses(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("del_exp@test.com")
            _make_expense(user.id)
            user_id = user.id
            db.session.commit()
            result = delete_user_pii(user_id)
            assert result["records_deleted"] >= 2  # user + expense
            remaining = Expense.query.filter_by(user_id=user_id).count()
            assert remaining == 0

    def test_delete_creates_audit_log(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("audit@test.com")
            email_hash = _hash_email(user.email)
            db.session.commit()
            result = delete_user_pii(user.id, reason="test_deletion")
            assert result["audit_log_id"] is not None
            log = DeletionAuditLog.query.filter_by(email_hash=email_hash).first()
            assert log is not None
            assert log.reason == "test_deletion"

    def test_delete_audit_log_contains_email_hash_not_email(self, app_fixture):
        with app_fixture.app_context():
            user = _make_user("privacy@test.com")
            db.session.commit()
            delete_user_pii(user.id)
            # Ensure we store hash, not plaintext email
            log = DeletionAuditLog.query.first()
            assert log is not None
            assert "@" not in log.email_hash  # It's a hash, not an email


# -----------------------------------------------------------------------
# API tests (require Redis)
# -----------------------------------------------------------------------

@requires_redis
class TestPiiGdprAPI:
    def test_export_json(self, client, auth_header):
        resp = client.get("/account/export", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_records" in data
        assert "sections" in data
        assert "checksum" in data

    def test_export_preview(self, client, auth_header):
        resp = client.get("/account/export/preview", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "export_preview" in data
        assert "total_records" in data

    def test_delete_without_confirm(self, client, auth_header):
        resp = client.delete("/account/delete",
                             json={"confirm": "nope"},
                             headers=auth_header)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "confirm" in data["error"]

    def test_delete_with_confirm(self, client, auth_header):
        resp = client.delete("/account/delete",
                             json={"confirm": "DELETE_MY_ACCOUNT"},
                             headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "permanently_deleted"
        assert data["irreversible"] is True

    def test_export_requires_auth(self, client):
        resp = client.get("/account/export")
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        resp = client.delete("/account/delete", json={"confirm": "DELETE_MY_ACCOUNT"})
        assert resp.status_code == 401