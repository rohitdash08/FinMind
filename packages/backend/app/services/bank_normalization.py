from __future__ import annotations

import re
from datetime import date
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Normalized transaction schema
# ---------------------------------------------------------------------------

@dataclass
class NormalizedTransaction:
    date: str                   # YYYY-MM-DD
    description: str            # cleaned description
    amount: float               # always positive
    type: str                   # "income" or "expense"
    currency: str               # ISO 4217 (default USD)
    category_hint: str          # auto-detected category hint
    original_row: dict          # raw input for audit trail


@dataclass
class NormalizationResult:
    normalized: list[NormalizedTransaction]
    rejected: list[dict]        # rows that couldn't be parsed
    total_rows: int
    success_count: int
    rejection_count: int
    detected_format: str
    summary: str


# ---------------------------------------------------------------------------
# Format detectors
# ---------------------------------------------------------------------------

# Common date formats, ordered by specificity
DATE_PATTERNS = [
    (r'^(\d{4})-(\d{2})-(\d{2})$', '%Y-%m-%d'),
    (r'^(\d{2})/(\d{2})/(\d{4})$', '%m/%d/%Y'),
    (r'^(\d{2})-(\d{2})-(\d{4})$', '%d-%m-%Y'),
    (r'^(\d{2})/(\d{2})/(\d{2})$', '%m/%d/%y'),
    (r'^(\d{1,2}) (\w+) (\d{4})$', '%d %B %Y'),
    (r'^(\d{1,2})-(\w+)-(\d{4})$', '%d-%b-%Y'),
]

# Category keyword mapping
CATEGORY_MAP = {
    "groceries": ["grocery", "supermarket", "walmart", "whole foods", "trader joe"],
    "dining": ["restaurant", "cafe", "starbucks", "mcdonald", "pizza", "sushi", "uber eats", "doordash"],
    "transport": ["uber", "lyft", "taxi", "bus", "metro", "transit", "parking", "gas", "fuel", "shell", "bp"],
    "utilities": ["electric", "gas company", "water", "internet", "cable", "phone", "verizon", "at&t", "comcast"],
    "rent": ["rent", "lease", "landlord", "apartment"],
    "healthcare": ["pharmacy", "cvs", "walgreen", "hospital", "doctor", "dental", "medical"],
    "entertainment": ["netflix", "spotify", "hulu", "youtube", "amazon prime", "cinema", "movie"],
    "shopping": ["amazon", "ebay", "target", "bestbuy", "apple store"],
    "income": ["payroll", "salary", "direct deposit", "transfer in", "payment received"],
}


def _normalize_date(raw_date: str) -> Optional[str]:
    """Try to parse a date string into YYYY-MM-DD."""
    from datetime import datetime
    raw = raw_date.strip()
    for pattern, fmt in DATE_PATTERNS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue
    return None


def _detect_category(description: str) -> str:
    """Detect a category hint from the transaction description."""
    desc_lower = description.lower()
    for cat, keywords in CATEGORY_MAP.items():
        if any(kw in desc_lower for kw in keywords):
            return cat
    return "other"


def _clean_description(raw: str) -> str:
    """Clean transaction description: remove reference IDs, normalize whitespace."""
    if not raw:
        return ""
    # Remove common noise patterns
    cleaned = re.sub(r'#\w+', '', raw)           # remove #ref codes
    cleaned = re.sub(r'\d{6,}', '', cleaned)      # remove long number sequences
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:200]  # cap at 200 chars


def _parse_amount(raw_amount) -> tuple[float, str]:
    """Parse amount and determine type (income/expense). Returns (amount, type)."""
    if raw_amount is None:
        return 0.0, "expense"

    raw = str(raw_amount).strip()

    # Handle debit/credit columns (already split)
    if isinstance(raw_amount, (int, float)):
        amount = float(raw_amount)
        tx_type = "income" if amount > 0 else "expense"
        return abs(amount), tx_type

    # Handle string formats: "(100.00)", "-100.00", "DR 100.00", "CR 100.00"
    is_credit = raw.startswith('CR') or raw.startswith('+')
    is_debit = raw.startswith('DR') or raw.startswith('-') or raw.startswith('(')

    # Remove non-numeric chars except dot
    numeric = re.sub(r'[^\d.]', '', raw)
    try:
        amount = float(numeric) if numeric else 0.0
    except ValueError:
        return 0.0, "expense"

    if is_credit:
        return amount, "income"
    return amount, "expense"


def _detect_format(rows: list[dict]) -> str:
    """Detect the input format based on column names."""
    if not rows:
        return "unknown"

    keys = {k.lower().strip() for k in rows[0].keys()}

    if "debit" in keys and "credit" in keys:
        return "debit_credit"
    if "amount" in keys and "type" in keys:
        return "amount_type"
    if "amount" in keys:
        return "single_amount"
    if "value" in keys:
        return "value_column"
    return "unknown"


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

def normalize_bank_statement(
    rows: list[dict],
    date_field: str = "date",
    description_field: str = "description",
    amount_field: str = "amount",
    type_field: Optional[str] = None,
    debit_field: Optional[str] = None,
    credit_field: Optional[str] = None,
    currency: str = "USD",
) -> NormalizationResult:
    """
    Normalize a list of raw bank statement rows into a unified transaction schema.

    Supports multiple statement formats:
    - Single amount column (negative = debit, positive = credit)
    - Separate debit + credit columns
    - Amount + type columns
    - Various date formats (ISO, US, EU, etc.)

    Args:
        rows: list of dicts representing raw statement rows
        date_field: name of the date column
        description_field: name of the description column
        amount_field: name of the amount column
        type_field: optional column name for transaction type
        debit_field: optional column name for debit amounts
        credit_field: optional column name for credit amounts
        currency: default currency code (ISO 4217)
    """
    if not rows:
        return NormalizationResult(
            normalized=[],
            rejected=[],
            total_rows=0,
            success_count=0,
            rejection_count=0,
            detected_format="unknown",
            summary="No rows provided for normalization.",
        )

    detected_format = _detect_format(rows)
    normalized: list[NormalizedTransaction] = []
    rejected: list[dict] = []

    for row in rows:
        # Case-insensitive field lookup
        row_lower = {k.lower().strip(): v for k, v in row.items()}

        # Get date
        raw_date = row_lower.get(date_field.lower()) or row_lower.get("date") or row_lower.get("transaction date") or ""
        norm_date = _normalize_date(str(raw_date)) if raw_date else None
        if not norm_date:
            rejected.append({"row": row, "reason": f"Could not parse date: '{raw_date}'"})
            continue

        # Get description
        raw_desc = (
            row_lower.get(description_field.lower())
            or row_lower.get("description")
            or row_lower.get("memo")
            or row_lower.get("narration")
            or ""
        )
        clean_desc = _clean_description(str(raw_desc))

        # Get amount and type
        if debit_field and credit_field:
            # Separate debit/credit columns
            raw_debit = row_lower.get(debit_field.lower(), 0) or 0
            raw_credit = row_lower.get(credit_field.lower(), 0) or 0
            try:
                debit_amt = float(str(raw_debit).replace(",", "").replace("$", "") or 0)
                credit_amt = float(str(raw_credit).replace(",", "").replace("$", "") or 0)
            except ValueError:
                debit_amt = credit_amt = 0.0

            if credit_amt > 0:
                amount, tx_type = credit_amt, "income"
            else:
                amount, tx_type = debit_amt, "expense"
        else:
            raw_amount = (
                row_lower.get(amount_field.lower())
                or row_lower.get("amount")
                or row_lower.get("value")
                or 0
            )
            # Clean amount string
            if isinstance(raw_amount, str):
                raw_amount = raw_amount.replace(",", "").replace("$", "").strip()
            amount, tx_type = _parse_amount(raw_amount)

        # Override type if type_field provided
        if type_field:
            raw_type = str(row_lower.get(type_field.lower(), "")).lower()
            if "credit" in raw_type or "income" in raw_type or "in" == raw_type:
                tx_type = "income"
            elif "debit" in raw_type or "expense" in raw_type or "out" == raw_type:
                tx_type = "expense"

        # Auto-detect category hint
        category_hint = _detect_category(clean_desc)
        if category_hint == "other" and tx_type == "income":
            category_hint = "income"

        normalized.append(
            NormalizedTransaction(
                date=norm_date,
                description=clean_desc,
                amount=round(amount, 2),
                type=tx_type,
                currency=currency.upper(),
                category_hint=category_hint,
                original_row=row,
            )
        )

    success_count = len(normalized)
    rejection_count = len(rejected)

    if rejection_count == 0:
        summary = f"Successfully normalized {success_count} transactions ({detected_format} format)."
    else:
        summary = (
            f"Normalized {success_count}/{len(rows)} transactions "
            f"({rejection_count} rejected due to parse errors). Format: {detected_format}."
        )

    return NormalizationResult(
        normalized=normalized,
        rejected=rejected,
        total_rows=len(rows),
        success_count=success_count,
        rejection_count=rejection_count,
        detected_format=detected_format,
        summary=summary,
    )