"""
Tests for database indexing optimization.
"""
import pytest
from app.db.indexes import (
    create_indexes,
    drop_indexes,
    get_indexes,
)
from app.extensions import db


class TestCreateIndexes:
    """Test create_indexes function."""

    def test_create_indexes(self, app):
        """Test that indexes are created successfully."""
        with app.app_context():
            # First drop any existing indexes
            drop_indexes()
            
            # Create indexes
            count = create_indexes()
            
            assert count == 9  # 9 indexes defined
            
            # Verify indexes exist
            indexes = get_indexes()
            assert "idx_expenses_user_id" in indexes
            assert "idx_expenses_user_date" in indexes
            assert "idx_expenses_user_category" in indexes
            assert "idx_expenses_spent_at" in indexes
            assert "idx_expenses_created_at" in indexes
            assert "idx_categories_user_id" in indexes
            assert "idx_recurring_user_active" in indexes
            assert "idx_bills_user_id" in indexes
            assert "idx_expenses_user_type_date" in indexes

    def test_create_indexes_idempotent(self, app):
        """Test that creating indexes twice doesn't fail."""
        with app.app_context():
            # Create indexes twice
            create_indexes()
            count = create_indexes()  # Should not raise
            
            assert count == 9


class TestDropIndexes:
    """Test drop_indexes function."""

    def test_drop_indexes(self, app):
        """Test that indexes are dropped successfully."""
        with app.app_context():
            # First create indexes
            create_indexes()
            
            # Drop indexes
            count = drop_indexes()
            
            assert count == 9
            
            # Verify indexes are gone
            indexes = get_indexes()
            assert "idx_expenses_user_id" not in indexes
            assert "idx_expenses_user_date" not in indexes

    def test_drop_indexes_idempotent(self, app):
        """Test that dropping indexes twice doesn't fail."""
        with app.app_context():
            # Drop indexes twice
            drop_indexes()
            count = drop_indexes()  # Should not raise
            
            assert count == 9


class TestGetIndexes:
    """Test get_indexes function."""

    def test_get_indexes_empty(self, app):
        """Test getting indexes when none exist."""
        with app.app_context():
            drop_indexes()
            indexes = get_indexes()
            
            # Should not contain our custom indexes
            custom_indexes = [i for i in indexes if i.startswith("idx_")]
            assert len(custom_indexes) == 0

    def test_get_indexes_after_create(self, app):
        """Test getting indexes after creation."""
        with app.app_context():
            create_indexes()
            indexes = get_indexes()
            
            # Should contain our custom indexes
            assert "idx_expenses_user_id" in indexes
            assert "idx_expenses_user_date" in indexes


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
