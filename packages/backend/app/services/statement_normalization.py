"""Universal bank statement normalization layer.

Normalizes different bank statement formats into a unified schema.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import logging

logger = logging.getLogger("finmind.normalization")

# Common date formats across banks
DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d, %Y",
]

# Column name mappings (bank-specific → normalized)
COLUMN_MAPPINGS = {
    # Amount columns
    "amount": "amount",
    "debit": "amount",
    "credit": "amount",
    "transaction amount": "amount",
    "value": "amount",
    # Date columns
    "date": "date",
    "transaction date": "date",
    "posting date": "date",
    "value date": "date",
    "txn date": "date",
    # Description columns
    "description": "description",
    "narration": "description",
    "particulars": "description",
    "details": "description",
    "memo": "description",
    "reference": "description",
    # Balance columns
    "balance": "balance",
    "closing balance": "balance",
    "running balance": "balance",
}


def normalize_statement(csv_content: str) -> dict:
    """Parse and normalize a bank statement CSV into unified format.

    Returns:
        {
            "transactions": [{date, amount, description, type, balance}],
            "metadata": {rows, date_range, format_detected},
            "errors": []
        }
    """
    errors = []
    transactions = []

    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        if not reader.fieldnames:
            return {"transactions": [], "errors": [{"message": "No headers found"}], "metadata": {}}

        # Map columns
        col_map = _detect_columns(reader.fieldnames)

        for i, row in enumerate(reader):
            try:
                txn = _normalize_row(row, col_map)
                if txn:
                    transactions.append(txn)
            except Exception as e:
                errors.append({"row": i + 2, "message": str(e)})

    except Exception as e:
        return {"transactions": [], "errors": [{"message": f"Parse error: {e}"}], "metadata": {}}

    dates = [t["date"] for t in transactions if t.get("date")]
    metadata = {
        "total_rows": len(transactions),
        "date_range": {"from": min(dates) if dates else None, "to": max(dates) if dates else None},
        "columns_detected": col_map,
    }

    return {"transactions": transactions, "metadata": metadata, "errors": errors}


def _detect_columns(fieldnames: list[str]) -> dict[str, str]:
    """Map CSV column names to normalized names."""
    mapping = {}
    for field in fieldnames:
        normalized = field.lower().strip()
        if normalized in COLUMN_MAPPINGS:
            mapping[field] = COLUMN_MAPPINGS[normalized]
    return mapping


def _normalize_row(row: dict, col_map: dict) -> dict | None:
    """Normalize a single CSV row."""
    result = {}

    for original_col, normalized_col in col_map.items():
        value = row.get(original_col, "").strip()
        if not value:
            continue

        if normalized_col == "date":
            result["date"] = _parse_date(value)
        elif normalized_col == "amount":
            result["amount"] = _parse_amount(value)
        elif normalized_col == "description":
            result["description"] = value
        elif normalized_col == "balance":
            result["balance"] = _parse_amount(value)

    if not result.get("amount"):
        return None

    # Determine type
    result["type"] = "INCOME" if result.get("amount", 0) > 0 else "EXPENSE"
    result["amount"] = abs(result.get("amount", 0))

    return result


def _parse_date(value: str) -> str | None:
    """Try multiple date formats."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> float | None:
    """Parse amount string handling various formats."""
    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[₹$€£¥,\s]', '', value)
    # Handle parentheses as negative
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        return float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None
