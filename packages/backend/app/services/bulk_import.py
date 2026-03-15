"""Bulk import validation and preview service.

Supports CSV and JSON imports with:
- Format detection and parsing
- Field validation with detailed error/warning reports
- Data correction suggestions (date normalization, category matching)
- Preview mode before committing imports
- Batch insert with rollback on failure
"""

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.extensions import db
from app.models import Category, Expense


# ── Supported date formats for auto-detection ──────────────────────
DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
]

# ── Field mapping aliases ──────────────────────────────────────────
FIELD_ALIASES = {
    "amount": ["amount", "total", "price", "cost", "value", "sum"],
    "date": ["date", "spent_at", "transaction_date", "txn_date", "when"],
    "category": ["category", "category_name", "type", "group"],
    "notes": ["notes", "description", "memo", "details", "note", "comment"],
    "currency": ["currency", "cur", "ccy"],
}


def _parse_date(value: str) -> Optional[date]:
    """Try multiple date formats and return parsed date or None."""
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_field_name(name: str) -> Optional[str]:
    """Map a column header to a canonical field name."""
    lower = name.strip().lower().replace(" ", "_")
    for canonical, aliases in FIELD_ALIASES.items():
        if lower in aliases:
            return canonical
    return None


def _match_category(name: str, user_categories: dict) -> Optional[int]:
    """Fuzzy match a category name to existing user categories."""
    lower = name.strip().lower()
    # Exact match first
    if lower in user_categories:
        return user_categories[lower]
    # Partial match
    for cat_name, cat_id in user_categories.items():
        if lower in cat_name or cat_name in lower:
            return cat_id
    return None


def parse_csv(content: str) -> list[dict]:
    """Parse CSV content into list of dicts."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        rows.append(dict(row))
    return rows


def parse_json(content: str) -> list[dict]:
    """Parse JSON content into list of dicts."""
    data = json.loads(content)
    if isinstance(data, dict) and "transactions" in data:
        data = data["transactions"]
    if isinstance(data, dict) and "expenses" in data:
        data = data["expenses"]
    if not isinstance(data, list):
        raise ValueError("JSON must be an array or contain a 'transactions'/'expenses' key")
    return data


def detect_format(content: str, filename: str = "") -> str:
    """Detect if content is CSV or JSON."""
    if filename.lower().endswith(".json"):
        return "json"
    if filename.lower().endswith(".csv"):
        return "csv"
    content_stripped = content.strip()
    if content_stripped.startswith(("{", "[")):
        return "json"
    return "csv"


def validate_and_preview(
    user_id: int,
    content: str,
    filename: str = "",
    file_format: str = "",
) -> dict:
    """Validate import data and return preview with warnings/corrections.

    Returns:
        {
            "format": "csv"|"json",
            "total_rows": int,
            "valid_rows": int,
            "invalid_rows": int,
            "rows": [...],
            "field_mapping": {...},
            "warnings": [...],
            "errors": [...],
            "summary": {...}
        }
    """
    fmt = file_format or detect_format(content, filename)

    # Parse
    try:
        if fmt == "json":
            raw_rows = parse_json(content)
        else:
            raw_rows = parse_csv(content)
    except Exception as e:
        return {
            "format": fmt,
            "total_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
            "rows": [],
            "field_mapping": {},
            "warnings": [],
            "errors": [f"Failed to parse {fmt.upper()} content: {str(e)}"],
            "summary": {},
        }

    if not raw_rows:
        return {
            "format": fmt,
            "total_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
            "rows": [],
            "field_mapping": {},
            "warnings": ["File contains no data rows"],
            "errors": [],
            "summary": {},
        }

    # Build field mapping from first row headers
    first_row = raw_rows[0]
    field_mapping = {}
    for col_name in first_row.keys():
        canonical = _normalize_field_name(col_name)
        if canonical:
            field_mapping[col_name] = canonical

    # Load user's categories for matching
    user_categories = {}
    cats = Category.query.filter_by(user_id=user_id).all()
    for cat in cats:
        user_categories[cat.name.lower()] = cat.id

    # Validate each row
    warnings = []
    errors = []
    valid_rows = []
    invalid_rows = []

    # Check required field mapping
    mapped_fields = set(field_mapping.values())
    if "amount" not in mapped_fields:
        errors.append("No 'amount' column found. Expected one of: " + ", ".join(FIELD_ALIASES["amount"]))
        return {
            "format": fmt,
            "total_rows": len(raw_rows),
            "valid_rows": 0,
            "invalid_rows": len(raw_rows),
            "rows": [],
            "field_mapping": field_mapping,
            "warnings": [],
            "errors": errors,
            "summary": {},
        }

    for idx, raw in enumerate(raw_rows, 1):
        row_errors = []
        row_warnings = []
        corrections = {}

        # Map fields
        mapped = {}
        for col_name, value in raw.items():
            canonical = _normalize_field_name(col_name)
            if canonical:
                mapped[canonical] = value
            else:
                row_warnings.append(f"Unknown column '{col_name}' — skipped")

        # Validate amount
        amount = None
        amount_str = mapped.get("amount", "").strip()
        if not amount_str:
            row_errors.append("Missing amount")
        else:
            # Remove currency symbols
            cleaned = amount_str.replace("$", "").replace("€", "").replace("£", "").replace("₹", "").replace(",", "").strip()
            try:
                amount = float(Decimal(cleaned))
                if amount <= 0:
                    row_warnings.append(f"Negative/zero amount ({amount}) — will be imported as-is")
                if cleaned != amount_str:
                    corrections["amount"] = f"Cleaned '{amount_str}' → {amount}"
            except (InvalidOperation, ValueError):
                row_errors.append(f"Invalid amount: '{amount_str}'")

        # Validate date
        parsed_date = None
        date_str = mapped.get("date", "").strip()
        if date_str:
            parsed_date = _parse_date(date_str)
            if parsed_date is None:
                row_errors.append(f"Unrecognized date format: '{date_str}'")
            elif parsed_date > date.today():
                row_warnings.append(f"Future date: {parsed_date}")
            elif parsed_date.year < 2000:
                row_warnings.append(f"Very old date: {parsed_date}")
        else:
            parsed_date = date.today()
            corrections["date"] = f"No date provided — defaulting to {parsed_date}"

        # Match category
        category_id = None
        category_name = mapped.get("category", "").strip()
        if category_name:
            category_id = _match_category(category_name, user_categories)
            if category_id is None:
                row_warnings.append(f"Unknown category '{category_name}' — will be created")
            elif category_name.lower() not in user_categories:
                corrections["category"] = f"Fuzzy matched '{category_name}' to existing category"

        # Notes
        notes = mapped.get("notes", "").strip()[:500] if mapped.get("notes") else None

        # Currency
        currency = mapped.get("currency", "INR").strip().upper()[:10]

        row_result = {
            "row_number": idx,
            "original": raw,
            "parsed": {
                "amount": amount,
                "date": str(parsed_date) if parsed_date else None,
                "category": category_name or None,
                "category_id": category_id,
                "notes": notes,
                "currency": currency,
            },
            "corrections": corrections,
            "warnings": row_warnings,
            "errors": row_errors,
            "valid": len(row_errors) == 0,
        }

        if row_errors:
            invalid_rows.append(row_result)
            for e in row_errors:
                errors.append(f"Row {idx}: {e}")
        else:
            valid_rows.append(row_result)

        for w in row_warnings:
            warnings.append(f"Row {idx}: {w}")

    # Summary stats
    valid_amounts = [r["parsed"]["amount"] for r in valid_rows if r["parsed"]["amount"] is not None]
    summary = {
        "total_amount": round(sum(valid_amounts), 2) if valid_amounts else 0,
        "average_amount": round(sum(valid_amounts) / len(valid_amounts), 2) if valid_amounts else 0,
        "min_amount": round(min(valid_amounts), 2) if valid_amounts else 0,
        "max_amount": round(max(valid_amounts), 2) if valid_amounts else 0,
        "categories_to_create": len([
            r for r in valid_rows
            if r["parsed"]["category"] and r["parsed"]["category_id"] is None
        ]),
        "rows_with_corrections": len([r for r in valid_rows if r["corrections"]]),
        "date_range": {
            "earliest": min(
                (r["parsed"]["date"] for r in valid_rows if r["parsed"]["date"]),
                default=None,
            ),
            "latest": max(
                (r["parsed"]["date"] for r in valid_rows if r["parsed"]["date"]),
                default=None,
            ),
        },
    }

    all_rows = valid_rows + invalid_rows
    all_rows.sort(key=lambda r: r["row_number"])

    return {
        "format": fmt,
        "total_rows": len(raw_rows),
        "valid_rows": len(valid_rows),
        "invalid_rows": len(invalid_rows),
        "rows": all_rows,
        "field_mapping": field_mapping,
        "warnings": warnings,
        "errors": errors,
        "summary": summary,
    }


def execute_import(
    user_id: int,
    content: str,
    filename: str = "",
    file_format: str = "",
    skip_invalid: bool = True,
    create_categories: bool = True,
) -> dict:
    """Execute the import after validation.

    Args:
        user_id: Authenticated user ID
        content: Raw file content
        filename: Original filename for format detection
        file_format: Force format ("csv" or "json")
        skip_invalid: Skip invalid rows instead of failing
        create_categories: Auto-create missing categories

    Returns:
        {
            "imported": int,
            "skipped": int,
            "categories_created": [...],
            "errors": [...],
            "total_amount": float,
        }
    """
    preview = validate_and_preview(user_id, content, filename, file_format)

    if preview["errors"] and not skip_invalid:
        return {
            "imported": 0,
            "skipped": 0,
            "categories_created": [],
            "errors": preview["errors"],
            "total_amount": 0,
        }

    imported = 0
    skipped = 0
    import_errors = []
    categories_created = []
    total_amount = 0

    # Cache for newly created categories
    new_categories = {}

    for row in preview["rows"]:
        if not row["valid"]:
            skipped += 1
            continue

        parsed = row["parsed"]

        # Resolve category
        category_id = parsed["category_id"]
        if parsed["category"] and category_id is None:
            if create_categories:
                cat_name = parsed["category"].strip()
                cat_lower = cat_name.lower()
                if cat_lower in new_categories:
                    category_id = new_categories[cat_lower]
                else:
                    cat = Category(user_id=user_id, name=cat_name)
                    db.session.add(cat)
                    db.session.flush()
                    category_id = cat.id
                    new_categories[cat_lower] = cat.id
                    categories_created.append(cat_name)

        try:
            expense = Expense(
                user_id=user_id,
                amount=parsed["amount"],
                spent_at=datetime.strptime(parsed["date"], "%Y-%m-%d").date() if parsed["date"] else date.today(),
                category_id=category_id,
                notes=parsed["notes"],
                currency=parsed["currency"],
            )
            db.session.add(expense)
            imported += 1
            total_amount += parsed["amount"]
        except Exception as e:
            skipped += 1
            import_errors.append(f"Row {row['row_number']}: {str(e)}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return {
            "imported": 0,
            "skipped": len(preview["rows"]),
            "categories_created": [],
            "errors": [f"Database error: {str(e)}"],
            "total_amount": 0,
        }

    return {
        "imported": imported,
        "skipped": skipped,
        "categories_created": categories_created,
        "errors": import_errors,
        "total_amount": round(total_amount, 2),
    }


def get_import_template(format_type: str = "csv") -> str:
    """Return a sample import template."""
    if format_type == "json":
        return json.dumps(
            {
                "transactions": [
                    {
                        "amount": "50.00",
                        "date": "2025-03-01",
                        "category": "Food",
                        "notes": "Lunch",
                        "currency": "INR",
                    },
                    {
                        "amount": "120.00",
                        "date": "2025-03-02",
                        "category": "Transport",
                        "notes": "Uber ride",
                    },
                ]
            },
            indent=2,
        )
    else:
        return "amount,date,category,notes,currency\n50.00,2025-03-01,Food,Lunch,INR\n120.00,2025-03-02,Transport,Uber ride,INR\n"
