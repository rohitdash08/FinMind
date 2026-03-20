"""Tests for Database Indexing Optimization service."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.db_indexing import (
    INDEX_DEFINITIONS,
    run_index_migration,
    get_index_health,
    _create_index,
    _index_exists,
)


def test_index_definitions_count():
    """We should have at least 8 index definitions."""
    assert len(INDEX_DEFINITIONS) >= 8


def test_index_definitions_have_required_fields():
    for idx in INDEX_DEFINITIONS:
        assert "name" in idx
        assert "table" in idx
        assert "columns" in idx
        assert "rationale" in idx
        assert len(idx["columns"]) >= 1


def test_index_definitions_unique_names():
    names = [idx["name"] for idx in INDEX_DEFINITIONS]
    assert len(names) == len(set(names))


def test_index_exists_returns_false_when_not_found():
    with patch("app.services.db_indexing.db") as mock_db:
        mock_db.session.execute.return_value.fetchone.return_value = None
        mock_db.text = MagicMock(return_value="")
        exists = _index_exists("nonexistent_index")
    assert exists is False


def test_index_exists_returns_true_when_found():
    with patch("app.services.db_indexing.db") as mock_db:
        mock_db.session.execute.return_value.fetchone.return_value = ("idx_name",)
        mock_db.text = MagicMock(return_value="")
        exists = _index_exists("some_index")
    assert exists is True


def test_create_index_success():
    with patch("app.services.db_indexing.db") as mock_db:
        mock_db.session.execute.return_value = MagicMock()
        mock_db.text = MagicMock(return_value="")
        success, err = _create_index(INDEX_DEFINITIONS[0])
    assert success is True
    assert err is None


def test_run_migration_all_new():
    """When no indexes exist, all should be created."""
    with patch("app.services.db_indexing.db") as mock_db, \
         patch("app.services.db_indexing._index_exists", return_value=False), \
         patch("app.services.db_indexing._create_index", return_value=(True, None)):
        report = run_index_migration()
    assert report.created == len(INDEX_DEFINITIONS)
    assert report.existing == 0
    assert report.failed == 0


def test_run_migration_all_existing():
    """When all indexes already exist, none should be created."""
    with patch("app.services.db_indexing._index_exists", return_value=True):
        report = run_index_migration()
    assert report.existing == len(INDEX_DEFINITIONS)
    assert report.created == 0


def test_get_index_health_structure():
    with patch("app.services.db_indexing._index_exists", return_value=True):
        health = get_index_health()
    assert "total_defined" in health
    assert "present" in health
    assert "missing" in health
    assert "health_pct" in health
    assert "indexes" in health
    assert health["health_pct"] == 100.0


def test_get_index_health_all_missing():
    with patch("app.services.db_indexing._index_exists", return_value=False):
        health = get_index_health()
    assert health["present"] == 0
    assert health["missing"] == len(INDEX_DEFINITIONS)
    assert health["health_pct"] == 0.0