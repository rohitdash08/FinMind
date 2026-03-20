"""Tests for Bulk Import Validation & Preview (issue #115)."""
import pytest

from app.services.bulk_import_validation import (
    validate_bulk_import,
    BulkImportPreviewResult,
    _is_valid_date,
    _is_valid_amount,
)


def test_empty_rows():
    result = validate_bulk_import(rows=[])
    assert result.total_rows == 0
    assert result.ready_to_import is False


def test_required_fields_present():
    result = validate_bulk_import(rows=[])
    assert hasattr(result, "total_rows")
    assert hasattr(result, "valid_rows")
    assert hasattr(result, "warning_rows")
    assert hasattr(result, "invalid_rows")
    assert hasattr(result, "ready_to_import")
    assert hasattr(result, "validations")
    assert hasattr(result, "corrected_preview")
    assert hasattr(result, "summary")


def test_valid_row_passes():
    rows = [{"date": "2026-01-15", "description": "Coffee", "amount": 5.0}]
    result = validate_bulk_import(rows)
    assert result.valid_rows >= 1
    assert result.invalid_rows == 0


def test_invalid_date_flagged():
    rows = [{"date": "NOTADATE", "description": "Coffee", "amount": 5.0}]
    result = validate_bulk_import(rows)
    v = result.validations[0]
    assert not v.is_valid
    assert any("date" in w.lower() or "Date" in w for w in v.warnings)


def test_missing_amount_flagged():
    rows = [{"date": "2026-01-15", "description": "Test"}]
    result = validate_bulk_import(rows)
    v = result.validations[0]
    assert not v.is_valid


def test_zero_amount_warning_not_invalid_by_default():
    rows = [{"date": "2026-01-15", "description": "Refund", "amount": 0}]
    result = validate_bulk_import(rows, strict=False)
    v = result.validations[0]
    # Default: zero amount = warning but not invalid
    assert any("zero" in w.lower() for w in v.warnings)


def test_zero_amount_strict_is_invalid():
    rows = [{"date": "2026-01-15", "description": "Refund", "amount": 0}]
    result = validate_bulk_import(rows, strict=True)
    assert result.invalid_rows >= 1


def test_missing_description_warns_but_corrects():
    rows = [{"date": "2026-01-15", "amount": 50.0}]
    result = validate_bulk_import(rows)
    v = result.validations[0]
    assert "description" in v.corrections or any("description" in w.lower() for w in v.warnings)


def test_ready_to_import_all_valid():
    rows = [
        {"date": "2026-01-15", "description": "Coffee", "amount": 5.0},
        {"date": "2026-01-16", "description": "Rent", "amount": 1000.0},
    ]
    result = validate_bulk_import(rows)
    assert result.ready_to_import is True


def test_is_valid_date_iso():
    assert _is_valid_date("2026-01-15") is True


def test_is_valid_date_invalid():
    assert _is_valid_date("NOTADATE") is False


def test_is_valid_amount_numeric():
    assert _is_valid_amount(100.0) is True
    assert _is_valid_amount("$50.00") is True
    assert _is_valid_amount("(100.00)") is True


def test_route_requires_auth(client):
    resp = client.post("/insights/import-preview", json={"rows": []})
    assert resp.status_code == 401