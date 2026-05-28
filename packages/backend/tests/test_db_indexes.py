"""
Tests for database indexing optimization.
"""

import pytest
from app.services.db_indexes import (
    INDEX_DEFINITIONS,
    create_missing_indexes,
    get_existing_indexes,
)


class TestDbIndexes:
    def test_index_definitions_exist(self):
        assert len(INDEX_DEFINITIONS) > 0
        for name, table, cols, unique in INDEX_DEFINITIONS:
            assert isinstance(name, str)
            assert isinstance(table, str)
            assert len(cols) > 0

    def test_create_missing_indexes(self, app, db_session):
        """Indexes should be created without errors."""
        with app.app_context():
            result = create_missing_indexes()
            assert result["total_defined"] == len(INDEX_DEFINITIONS)
            assert len(result["errors"]) == 0

    def test_idempotent_creation(self, app, db_session):
        """Running twice should skip existing indexes."""
        with app.app_context():
            r1 = create_missing_indexes()
            r2 = create_missing_indexes()
            # Second run should have more skipped
            assert len(r2["skipped"]) >= len(r1["skipped"])

    def test_existing_indexes_check(self, app, db_session):
        """get_existing_indexes should return a set."""
        with app.app_context():
            indexes = get_existing_indexes("expenses")
            assert isinstance(indexes, set)

    def test_expense_composite_indexes(self):
        """Verify critical composite indexes exist."""
        expense_indexes = [(n, t, c) for n, t, c, _ in INDEX_DEFINITIONS if t == "expenses"]
        # Should have user+date composite
        has_user_date = any("user_id" in c and "spent_at" in c and len(c) > 1 for _, _, c in expense_indexes)
        assert has_user_date, "Missing composite index on expenses(user_id, spent_at)"
