"""
Tests for secure backup and encrypted export.
"""
import pytest
import gzip
import json
from cryptography.fernet import Fernet
from app.services.backup import (
    create_backup,
    validate_encryption_key,
    verify_backup,
    get_backup_metadata,
)
from app.models import User, Expense, Category
from app.extensions import db
from decimal import Decimal
from datetime import datetime


class TestValidateEncryptionKey:
    """Test validate_encryption_key function."""

    def test_valid_key(self):
        """Test valid Fernet key."""
        key = Fernet.generate_key()
        assert validate_encryption_key(key) is True

    def test_invalid_key(self):
        """Test invalid key format."""
        assert validate_encryption_key(b"invalid-key") is False

    def test_empty_key(self):
        """Test empty key."""
        assert validate_encryption_key(b"") is False


class TestCreateBackup:
    """Test create_backup function."""

    def test_backup_without_encryption(self, app, db, sample_user):
        """Test creating unencrypted backup."""
        with app.app_context():
            backup = create_backup(user_id=sample_user.id)
            
            # Should be gzip compressed
            decompressed = gzip.decompress(backup)
            data = json.loads(decompressed)
            
            assert data["version"] == "1.0"
            assert data["user_id"] == sample_user.id
            assert "user_profile" in data
            assert "expenses" in data
            assert "categories" in data

    def test_backup_with_encryption(self, app, db, sample_user):
        """Test creating encrypted backup."""
        with app.app_context():
            key = Fernet.generate_key()
            backup = create_backup(user_id=sample_user.id, encryption_key=key)
            
            # Should be encrypted (not directly decompressible)
            with pytest.raises(Exception):
                gzip.decompress(backup)
            
            # Decrypt and verify
            f = Fernet(key)
            decrypted = f.decrypt(backup)
            decompressed = gzip.decompress(decrypted)
            data = json.loads(decompressed)
            
            assert data["user_id"] == sample_user.id

    def test_backup_invalid_user(self, app, db):
        """Test backup with non-existent user."""
        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                create_backup(user_id=999)

    def test_backup_invalid_key(self, app, db, sample_user):
        """Test backup with invalid encryption key."""
        with app.app_context():
            with pytest.raises(ValueError, match="Invalid encryption key"):
                create_backup(user_id=sample_user.id, encryption_key=b"invalid")

    def test_backup_with_expenses(self, app, db, sample_user, sample_category):
        """Test backup includes expenses."""
        with app.app_context():
            exp = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("100.50"),
                spent_at=datetime(2024, 1, 15),
                notes="Test expense"
            )
            db.session.add(exp)
            db.session.commit()
            
            backup = create_backup(user_id=sample_user.id)
            decompressed = gzip.decompress(backup)
            data = json.loads(decompressed)
            
            assert len(data["expenses"]) == 1
            assert data["expenses"][0]["amount"] == "100.50"
            assert data["expenses"][0]["notes"] == "Test expense"


class TestVerifyBackup:
    """Test verify_backup function."""

    def test_valid_checksum(self, app, db, sample_user):
        """Test backup verification with valid checksum."""
        with app.app_context():
            backup = create_backup(user_id=sample_user.id)
            import hashlib
            checksum = hashlib.sha256(backup).hexdigest()
            
            assert verify_backup(backup, checksum) is True

    def test_invalid_checksum(self, app, db, sample_user):
        """Test backup verification with invalid checksum."""
        with app.app_context():
            backup = create_backup(user_id=sample_user.id)
            
            assert verify_backup(backup, "invalid-checksum") is False


class TestGetBackupMetadata:
    """Test get_backup_metadata function."""

    def test_metadata_unencrypted(self, app, db, sample_user):
        """Test getting metadata from unencrypted backup."""
        with app.app_context():
            backup = create_backup(user_id=sample_user.id)
            metadata = get_backup_metadata(backup)
            
            assert metadata["version"] == "1.0"
            assert metadata["user_id"] == sample_user.id
            assert "created_at" in metadata

    def test_metadata_encrypted_fails(self, app, db, sample_user):
        """Test that metadata extraction fails for encrypted backup."""
        with app.app_context():
            key = Fernet.generate_key()
            backup = create_backup(user_id=sample_user.id, encryption_key=key)
            metadata = get_backup_metadata(backup)
            
            assert "error" in metadata


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
    """Create a sample user."""
    with app.app_context():
        user = User(email="test@example.com", currency="USD")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def sample_category(app, db, sample_user):
    """Create a sample category."""
    with app.app_context():
        category = Category(name="General", user_id=sample_user.id)
        db.session.add(category)
        db.session.commit()
        return category
