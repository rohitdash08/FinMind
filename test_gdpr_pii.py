"""
Tests for GDPR PII export and delete workflow.
"""
import pytest
from datetime import datetime
from app.services.gdpr_pii import (
    export_user_pii,
    delete_user_pii,
    anonymize_user_data,
    get_pii_export_status,
)
from app.extensions import db


class TestExportUserPII:
    """Test export_user_pii function."""

    def test_export_user_pii_success(self, app, db, sample_user):
        with app.app_context():
            result = export_user_pii(user_id=sample_user.id)

            assert result["status"] == "success"
            assert "export_id" in result
            assert "data" in result

            # Verify export contains expected fields
            export_data = result["data"]
            assert "personal_info" in export_data
            assert "financial_data" in export_data
            assert "activity_logs" in export_data

    def test_export_user_pii_not_found(self, app, db):
        with app.app_context():
            result = export_user_pii(user_id=999)

            assert result["status"] == "error"
            assert "not found" in result["message"].lower()

    def test_export_user_pii_empty_data(self, app, db, sample_user_no_data):
        with app.app_context():
            result = export_user_pii(user_id=sample_user_no_data.id)

            assert result["status"] == "success"
            assert result["data"]["financial_data"] == []
            assert result["data"]["activity_logs"] == []


class TestDeleteUserPII:
    """Test delete_user_pii function."""

    def test_delete_user_pii_success(self, app, db, sample_user):
        with app.app_context():
            # First export
            export_result = export_user_pii(user_id=sample_user.id)
            export_id = export_result["export_id"]

            # Then delete
            result = delete_user_pii(user_id=sample_user.id, export_id=export_id)

            assert result["status"] == "success"
            assert result["deleted_records"] > 0

            # Verify user is anonymized
            user = User.query.get(sample_user.id)
            assert user.email != sample_user.email
            assert user.name != sample_user.name

    def test_delete_user_pii_without_export(self, app, db, sample_user):
        with app.app_context():
            result = delete_user_pii(user_id=sample_user.id, export_id=None)

            # Should still work but warn
            assert result["status"] == "success"
            assert "warning" in result

    def test_delete_user_pii_not_found(self, app, db):
        with app.app_context():
            result = delete_user_pii(user_id=999, export_id=None)

            assert result["status"] == "error"
            assert "not found" in result["message"].lower()

    def test_delete_user_pii_already_deleted(self, app, db, sample_user):
        with app.app_context():
            # Delete once
            delete_user_pii(user_id=sample_user.id, export_id=None)

            # Try to delete again
            result = delete_user_pii(user_id=sample_user.id, export_id=None)

            assert result["status"] == "error"
            assert "already" in result["message"].lower()


class TestAnonymizeUserData:
    """Test anonymize_user_data function."""

    def test_anonymize_user_data(self, app, db, sample_user):
        with app.app_context():
            original_email = sample_user.email
            original_name = sample_user.name

            anonymize_user_data(user_id=sample_user.id)

            user = User.query.get(sample_user.id)
            assert user.email != original_email
            assert user.name != original_name
            assert "anonymized" in user.email.lower()
            assert "anonymized" in user.name.lower()

    def test_anonymize_preserves_structure(self, app, db, sample_user):
        with app.app_context():
            anonymize_user_data(user_id=sample_user.id)

            user = User.query.get(sample_user.id)
            # User should still exist
            assert user is not None
            # But data should be anonymized
            assert user.email != sample_user.email

    def test_anonymize_financial_data(self, app, db, sample_user_with_transactions):
        with app.app_context():
            anonymize_user_data(user_id=sample_user_with_transactions.id)

            # Transactions should be anonymized but preserved
            transactions = Transaction.query.filter_by(
                user_id=sample_user_with_transactions.id
            ).all()

            for tx in transactions:
                assert tx.description != "Original description"
                assert "anonymized" in tx.description.lower()


class TestGetPIIExportStatus:
    """Test get_pii_export_status function."""

    def test_get_export_status_pending(self, app, db, sample_user):
        with app.app_context():
            # Start export
            export_result = export_user_pii(user_id=sample_user.id)
            export_id = export_result["export_id"]

            # Check status
            status = get_pii_export_status(export_id=export_id)

            assert status["status"] in ["pending", "processing", "completed"]
            assert "progress" in status

    def test_get_export_status_completed(self, app, db, sample_user):
        with app.app_context():
            # Complete export
            export_result = export_user_pii(user_id=sample_user.id)
            export_id = export_result["export_id"]

            # Check status
            status = get_pii_export_status(export_id=export_id)

            assert status["status"] == "completed"
            assert status["progress"] == 100

    def test_get_export_status_not_found(self, app, db):
        with app.app_context():
            status = get_pii_export_status(export_id="nonexistent")

            assert status["status"] == "error"
            assert "not found" in status["message"].lower()


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app

    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db(app):
    """Create database for testing."""
    with app.app_context():
        yield db


@pytest.fixture
def sample_user(app, db):
    """Create sample user for testing."""
    from app.models import User

    with app.app_context():
        user = User(
            email="test@example.com",
            name="Test User",
            password_hash="hashed_password",
        )
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def sample_user_no_data(app, db):
    """Create sample user with no financial data."""
    from app.models import User

    with app.app_context():
        user = User(
            email="empty@example.com",
            name="Empty User",
            password_hash="hashed_password",
        )
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def sample_user_with_transactions(app, db, sample_user):
    """Create sample user with transactions."""
    from app.models import Transaction

    with app.app_context():
        for i in range(5):
            tx = Transaction(
                user_id=sample_user.id,
                amount=100.00 + i,
                description=f"Transaction {i}",
                category="food",
                date=datetime.now(),
            )
            db.session.add(tx)
        db.session.commit()
        return sample_user
