from __future__ import annotations

import re
from datetime import date
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RowValidation:
    row_index: int
    is_valid: bool
    warnings: list[str]
    corrections: dict          # suggested corrections: field -> value
    original: dict


@dataclass
class BulkImportPreviewResult:
    total_rows: int
    valid_rows: int
    warning_rows: int
    invalid_rows: int
    validations: list[RowValidation]
    corrected_preview: list[dict]     # rows with auto-corrections applied
    schema_detected: dict             # detected field mappings
    summary: str
    ready_to_import: bool


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

def _is_valid_date(value: str) -> bool:
    """Check if value parses as a date in common formats."""
    from app.services.bank_normalization import _normalize_date
    return _normalize_date(str(value)) is not None


def _is_valid_amount(value) -> bool:
    """Check if value can be parsed as a numeric amount."""
    if value is None:
        return False
    cleaned = re.sub(r'[$,€£¥\s\(\)]', '', str(value)).strip()
    if not cleaned:
        return False
    try:
        float(cleaned.lstrip('-+').replace('DR', '').replace('CR', ''))
        return True
    except ValueError:
        return False


def _parse_amount_value(value) -> float:
    """Parse amount, returning 0.0 on failure."""
    cleaned = re.sub(r'[$,€£¥\s]', '', str(value)).strip()
    is_negative = cleaned.startswith('(') or cleaned.startswith('-') or 'DR' in cleaned.upper()
    cleaned = re.sub(r'[^\d.]', '', cleaned)
    try:
        amount = float(cleaned)
        return -amount if is_negative else amount
    except ValueError:
        return 0.0


def _suggest_date_correction(value: str) -> Optional[str]:
    """Try to correct a malformed date."""
    from app.services.bank_normalization import _normalize_date
    return _normalize_date(str(value))


def _detect_schema(rows: list[dict]) -> dict:
    """Auto-detect which columns map to date/amount/description."""
    if not rows:
        return {}

    sample = rows[0]
    schema = {}

    for key, value in sample.items():
        key_lower = key.lower().strip()

        # Date detection
        if any(kw in key_lower for kw in ['date', 'time', 'when', 'posted']):
            if _is_valid_date(str(value)):
                schema['date'] = key
        # Amount detection
        elif any(kw in key_lower for kw in ['amount', 'value', 'total', 'sum', 'price']):
            if _is_valid_amount(value):
                schema['amount'] = key
        # Description detection
        elif any(kw in key_lower for kw in ['desc', 'memo', 'note', 'narration', 'payee', 'merchant', 'reference']):
            schema['description'] = key

    return schema


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

def validate_bulk_import(
    rows: list[dict],
    date_field: str = "date",
    amount_field: str = "amount",
    description_field: str = "description",
    strict: bool = False,
) -> BulkImportPreviewResult:
    """
    Validate a batch of transaction rows before import, showing warnings and corrections.

    Args:
        rows: raw input rows to validate
        date_field: column name for date
        amount_field: column name for amount
        description_field: column name for description
        strict: if True, zero-amount rows are invalid (not just warnings)
    """
    if not rows:
        return BulkImportPreviewResult(
            total_rows=0,
            valid_rows=0,
            warning_rows=0,
            invalid_rows=0,
            validations=[],
            corrected_preview=[],
            schema_detected={},
            summary="No rows to validate.",
            ready_to_import=False,
        )

    schema = _detect_schema(rows)
    # Override with explicit fields
    if date_field:
        schema['date'] = date_field
    if amount_field:
        schema['amount'] = amount_field

    validations: list[RowValidation] = []
    corrected_rows: list[dict] = []

    for idx, row in enumerate(rows):
        row_lower = {k.lower().strip(): v for k, v in row.items()}
        warnings: list[str] = []
        corrections: dict = {}
        is_invalid = False

        # --- Date validation ---
        df = schema.get('date', date_field).lower()
        raw_date = row_lower.get(df, row_lower.get('date', ''))
        if not raw_date:
            warnings.append(f"Missing date in field '{df}'.")
            is_invalid = True
        elif not _is_valid_date(str(raw_date)):
            corrected = _suggest_date_correction(str(raw_date))
            if corrected:
                warnings.append(f"Date '{raw_date}' corrected to '{corrected}'.")
                corrections['date'] = corrected
            else:
                warnings.append(f"Invalid date format: '{raw_date}'. Could not auto-correct.")
                is_invalid = True

        # --- Amount validation ---
        af = schema.get('amount', amount_field).lower()
        raw_amount = row_lower.get(af, row_lower.get('amount', None))
        if raw_amount is None:
            warnings.append(f"Missing amount in field '{af}'.")
            is_invalid = True
        elif not _is_valid_amount(raw_amount):
            warnings.append(f"Could not parse amount: '{raw_amount}'.")
            is_invalid = True
        else:
            parsed = _parse_amount_value(raw_amount)
            if parsed == 0.0:
                if strict:
                    is_invalid = True
                warnings.append("Amount is zero.")
            # Suggest clean amount
            if str(raw_amount) != str(parsed):
                corrections['amount'] = parsed

        # --- Description check ---
        dfield = schema.get('description', description_field).lower()
        raw_desc = row_lower.get(dfield, row_lower.get('description', ''))
        if not raw_desc:
            warnings.append("Missing description — will use 'Unknown' as fallback.")
            corrections['description'] = 'Unknown'

        # Build corrected row
        corrected = dict(row)
        for field_name, corrected_val in corrections.items():
            # Find original key (case-insensitive match)
            for orig_key in row:
                if orig_key.lower().strip() == field_name.lower():
                    corrected[orig_key] = corrected_val
                    break
        corrected_rows.append(corrected)

        validations.append(
            RowValidation(
                row_index=idx,
                is_valid=not is_invalid,
                warnings=warnings,
                corrections=corrections,
                original=row,
            )
        )

    valid_count = sum(1 for v in validations if v.is_valid and not v.warnings)
    warning_count = sum(1 for v in validations if v.is_valid and v.warnings)
    invalid_count = sum(1 for v in validations if not v.is_valid)
    ready = invalid_count == 0

    summary = (
        f"{valid_count} clean rows, {warning_count} with warnings, {invalid_count} invalid "
        f"out of {len(rows)} total. "
        + ("Ready to import." if ready else f"Fix {invalid_count} invalid row(s) before importing.")
    )

    return BulkImportPreviewResult(
        total_rows=len(rows),
        valid_rows=valid_count,
        warning_rows=warning_count,
        invalid_rows=invalid_count,
        validations=validations,
        corrected_preview=corrected_rows,
        schema_detected=schema,
        summary=summary,
        ready_to_import=ready,
    )