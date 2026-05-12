"""Bulk import validation & preview improvements."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import logging

logger = logging.getLogger("finmind.bulk_import")

REQUIRED_FIELDS = ["amount", "spent_at"]
OPTIONAL_FIELDS = ["notes", "category", "currency", "expense_type"]
VALID_EXPENSE_TYPES = {"EXPENSE", "INCOME"}
MAX_ROWS = 1000


def validate_import(rows: list[dict[str, Any]]) -> dict:
    """Validate bulk import data and return preview with errors.

    Returns:
        {
            "valid": bool,
            "total_rows": int,
            "valid_rows": int,
            "error_rows": int,
            "errors": [{row, field, message}],
            "preview": [first 5 valid rows],
            "summary": {total_amount, date_range, categories}
        }
    """
    if not rows:
        return {"valid": False, "errors": [{"row": 0, "field": "data", "message": "No data provided"}]}

    if len(rows) > MAX_ROWS:
        return {"valid": False, "errors": [{"row": 0, "field": "data", "message": f"Max {MAX_ROWS} rows allowed"}]}

    errors = []
    valid_rows = []

    for i, row in enumerate(rows):
        row_errors = _validate_row(i + 1, row)
        if row_errors:
            errors.extend(row_errors)
        else:
            valid_rows.append(row)

    # Summary
    total_amount = sum(float(r["amount"]) for r in valid_rows)
    dates = [r["spent_at"] for r in valid_rows if r.get("spent_at")]
    categories = list(set(r.get("category", "Uncategorized") for r in valid_rows))

    return {
        "valid": len(errors) == 0,
        "total_rows": len(rows),
        "valid_rows": len(valid_rows),
        "error_rows": len(rows) - len(valid_rows),
        "errors": errors[:50],  # Limit error output
        "preview": valid_rows[:5],
        "summary": {
            "total_amount": round(total_amount, 2),
            "date_range": {"from": min(dates) if dates else None, "to": max(dates) if dates else None},
            "categories": categories[:20],
        },
    }


def _validate_row(row_num: int, row: dict) -> list[dict]:
    """Validate a single import row."""
    errors = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in row or not row[field]:
            errors.append({"row": row_num, "field": field, "message": f"{field} is required"})

    if errors:
        return errors

    # Validate amount
    try:
        amount = Decimal(str(row["amount"]))
        if amount == 0:
            errors.append({"row": row_num, "field": "amount", "message": "amount cannot be zero"})
    except (InvalidOperation, ValueError):
        errors.append({"row": row_num, "field": "amount", "message": "invalid amount format"})

    # Validate date
    try:
        if isinstance(row["spent_at"], str):
            date.fromisoformat(row["spent_at"])
    except ValueError:
        errors.append({"row": row_num, "field": "spent_at", "message": "invalid date format (use YYYY-MM-DD)"})

    # Validate expense_type
    if row.get("expense_type") and row["expense_type"].upper() not in VALID_EXPENSE_TYPES:
        errors.append({"row": row_num, "field": "expense_type", "message": f"must be one of: {VALID_EXPENSE_TYPES}"})

    return errors
