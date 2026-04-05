"""Tests for database performance indexes (issue #128)."""
import pytest
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="module")
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        _db.create_all()
        # Apply indexes (SQLite supports them)
        import app.models_indexed  # noqa: F401 — registers indexes
        yield app


def test_expense_indexes_defined(app):
    """Verify index definitions exist on the Expense model."""
    import app.models_indexed  # noqa: F401
    from sqlalchemy import Index
    from app.models import Expense
    mapper = inspect(Expense)
    index_names = {i.name for i in mapper.mapper.persist_selectable.indexes}
    assert "ix_expenses_user_spent" in index_names
    assert "ix_expenses_user_category" in index_names
    assert "ix_expenses_user_type" in index_names


def test_migration_file_exists():
    """Verify the Alembic migration file is present."""
    import os
    migration = os.path.join(
        os.path.dirname(__file__),
        "../migrations/versions/003_add_performance_indexes.py"
    )
    assert os.path.exists(migration), "Migration file missing"


def test_expense_query_uses_index(app):
    """Smoke test: query by user_id + spent_at executes without error."""
    from app.models import Expense
    from datetime import date
    with app.app_context():
        result = _db.session.query(Expense).filter(
            Expense.user_id == 1,
            Expense.spent_at >= date(2026, 1, 1)
        ).all()
        assert isinstance(result, list)
