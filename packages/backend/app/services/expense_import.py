import csv
import io
import json
import re
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


# ---------------------------------------------------------------------------
# Validation data classes
# ---------------------------------------------------------------------------


@dataclass
class RowValidationResult:
    """Result of validating a single import row."""

    row_index: int
    is_valid: bool  # True if row can be imported (warnings OK, errors not OK)
    has_errors: bool  # True if row has blocking errors
    warnings: list[str] = field(default_factory=list)
    corrections: dict[str, Any] = field(default_factory=dict)
    original: dict[str, Any] = field(default_factory=dict)


@dataclass
class BulkImportValidationResult:
    """Aggregated result of validating all import rows."""

    total_rows: int
    valid_rows: int
    warning_rows: int  # rows with warnings but no errors
    error_rows: int  # rows with blocking errors
    ready_to_import: bool  # True if all rows can be imported
    row_results: list[RowValidationResult]
    corrected_preview: list[dict[str, Any]]  # rows with auto-corrections applied


# ---------------------------------------------------------------------------
# Public validation API
# ---------------------------------------------------------------------------


def validate_import_rows(
    rows: list[dict[str, Any]],
    strict: bool = False,
) -> BulkImportValidationResult:
    """
    Validate a list of normalized import rows.

    Args:
        rows: List of transaction dicts (already run through normalize_import_rows).
        strict: If True, zero amounts and future dates are treated as errors.
                If False, they are warnings only.

    Returns:
        BulkImportValidationResult with per-row validation details.
    """
    if not rows:
        return BulkImportValidationResult(
            total_rows=0,
            valid_rows=0,
            warning_rows=0,
            error_rows=0,
            ready_to_import=False,
            row_results=[],
            corrected_preview=[],
        )

    row_results: list[RowValidationResult] = []
    today = date.today()
    max_date = today + timedelta(days=1)  # allow 1 day future for timezone edge cases
    min_date = date(1990, 1, 1)

    for idx, row in enumerate(rows):
        vr = _validate_row(
            row, idx, today, min_date, max_date, strict
        )
        row_results.append(vr)

    valid_rows = sum(1 for r in row_results if r.is_valid)
    warning_rows = sum(1 for r in row_results if not r.has_errors and r.warnings)
    error_rows = sum(1 for r in row_results if r.has_errors)
    ready = all(r.is_valid for r in row_results)

    # Build corrected preview: apply corrections to each row
    corrected_preview = []
    for vr in row_results:
        if vr.corrections:
            corrected = dict(vr.original)
            corrected.update(vr.corrections)
            corrected_preview.append(corrected)
        else:
            corrected_preview.append(dict(vr.original))

    return BulkImportValidationResult(
        total_rows=len(rows),
        valid_rows=valid_rows,
        warning_rows=warning_rows,
        error_rows=error_rows,
        ready_to_import=ready,
        row_results=row_results,
        corrected_preview=corrected_preview,
    )


def _validate_row(
    row: dict[str, Any],
    idx: int,
    today: date,
    min_date: date,
    max_date: date,
    strict: bool,
) -> RowValidationResult:
    """Validate a single row, returning errors, warnings, and corrections."""
    warnings: list[str] = []
    corrections: dict[str, Any] = {}
    has_errors = False

    # --- Date validation ---
    raw_date = row.get("date")
    date_val = _parse_date(raw_date)
    if date_val is None:
        warnings.append(f"Row {idx + 1}: Invalid or missing date '{raw_date}'")
        has_errors = True
    elif date_val > max_date:
        msg = f"Row {idx + 1}: Date '{date_val}' is in the future"
        if strict:
            warnings.append(msg)
            has_errors = True
        else:
            warnings.append(msg + " (warning only)")
    elif date_val < min_date:
        warnings.append(
            f"Row {idx + 1}: Date '{date_val}' is very old "
            f"(before {min_date.year}). Verify this is intentional."
        )

    # --- Amount validation ---
    raw_amount = row.get("amount")
    amount_val = _parse_float(raw_amount)
    if amount_val is None:
        warnings.append(f"Row {idx + 1}: Invalid or missing amount '{raw_amount}'")
        has_errors = True
    elif amount_val == 0:
        msg = f"Row {idx + 1}: Amount is zero"
        if strict:
            warnings.append(msg)
            has_errors = True
        else:
            warnings.append(msg + " (allowed as zero-value entry)")
    elif amount_val < 0:
        warnings.append(
            f"Row {idx + 1}: Negative amount '{raw_amount}' stored as absolute value"
        )
        corrections["amount"] = abs(amount_val)

    # Flag unusually large amounts as warnings
    if amount_val is not None and amount_val > 100_000:
        warnings.append(
            f"Row {idx + 1}: Unusually large amount {amount_val:.2f}. "
            "Verify this is correct."
        )

    # --- Description validation ---
    desc = row.get("description") or ""
    if not str(desc).strip():
        warnings.append(f"Row {idx + 1}: Missing description; using 'Unknown'")
        corrections["description"] = "Unknown"
    elif len(str(desc).strip()) < 2:
        warnings.append(
            f"Row {idx + 1}: Description '{desc}' is very short; "
            "it may be misparsed."
        )

    # --- Expense type validation ---
    etype = str(row.get("expense_type") or "").upper().strip()
    if etype not in ("EXPENSE", "INCOME"):
        corrections["expense_type"] = "EXPENSE"
        warnings.append(
            f"Row {idx + 1}: Unknown expense_type '{etype}', defaulting to 'EXPENSE'"
        )

    # --- Currency validation ---
    currency = str(row.get("currency") or "").strip().upper()
    if not currency:
        corrections["currency"] = "USD"
        warnings.append(
            f"Row {idx + 1}: Missing currency code, defaulting to 'USD'"
        )
    elif len(currency) != 3:
        warnings.append(
            f"Row {idx + 1}: Currency '{currency}' does not look like a "
            "3-letter ISO code; verify it is correct."
        )

    # Row is valid for import if no blocking errors
    is_valid = not has_errors

    return RowValidationResult(
        row_index=idx,
        is_valid=is_valid,
        has_errors=has_errors,
        warnings=warnings,
        corrections=corrections,
        original=dict(row),
    )


# ---------------------------------------------------------------------------
# Row extraction from raw files
# ---------------------------------------------------------------------------


def extract_transactions_from_statement(
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    gemini_api_key: str | None,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
) -> list[dict[str, Any]]:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if name.endswith(".csv") or "csv" in ctype:
        return _parse_csv_rows(data)
    if name.endswith(".pdf") or "pdf" in ctype:
        text = _extract_pdf_text(data)
        if gemini_api_key:
            try:
                ai_rows = _extract_with_gemini(text, gemini_api_key, gemini_model)
                if normalize_import_rows(ai_rows):
                    return ai_rows
            except Exception:
                pass
        return _extract_pdf_rows_fallback(text)
    raise ValueError("Only PDF and CSV files are supported")


def normalize_import_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        dt = _normalize_date(row.get("date"))
        amt = _normalize_amount(row.get("amount"))
        desc = str(row.get("description") or "").strip()
        if not dt or amt is None or not desc:
            continue
        expense_type = _infer_expense_type(row.get("expense_type"), desc, amt)
        cid = row.get("category_id")
        category_id = int(cid) if cid not in (None, "", "null") else None
        normalized.append(
            {
                "date": dt,
                "amount": float(abs(amt)),
                "description": desc[:500],
                "category_id": category_id,
                "expense_type": expense_type,
                "currency": str(row.get("currency") or "USD")[:10],
            }
        )
    return normalized


def _parse_csv_rows(data: bytes) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict[str, Any]] = []
    for row in reader:
        out.append(
            {
                "date": row.get("date") or row.get("spent_at"),
                "amount": row.get("amount"),
                "description": row.get("description") or row.get("notes"),
                "category_id": row.get("category_id"),
                "currency": row.get("currency") or "USD",
            }
        )
    return out


def _extract_pdf_text(data: bytes) -> str:
    if not PdfReader:
        raise ValueError("PDF extraction dependency missing (pypdf)")
    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError("PDF has no readable text")
    return text


def _extract_with_gemini(
    text: str,
    api_key: str | None,
    model: str,
) -> list[dict[str, Any]]:
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured")
    prompt = (
        "You are FinMind's data-extraction persona: "
        "a meticulous bank statement analyst. "
        "Extract transactions and return ONLY JSON array. "
        "Each item: date(YYYY-MM-DD), amount(number), "
        "description(string), category_id(null), currency('USD'). "
        "Ignore balances, totals, and non-transaction rows. "
        "Do not include markdown.\n\n"
        f"STATEMENT_TEXT:\n{text[:120000]}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    resp = requests.post(
        url,
        params={"key": api_key},
        json={
            "generationConfig": {"temperature": 0},
            "contents": [{"parts": [{"text": prompt}]}],
        },
        timeout=45,
    )
    resp.raise_for_status()
    payload = resp.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        return []
    parts = (
        candidates[0].get("content", {}).get("parts", [])
        if isinstance(candidates[0], dict)
        else []
    )
    text_blob = "\n".join(
        str(part.get("text") or "") for part in parts if isinstance(part, dict)
    ).strip()
    return _parse_transactions_json(text_blob)


def _parse_transactions_json(text: str) -> list[dict[str, Any]]:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*\])\s*```", candidate, flags=re.S)
    if fenced:
        candidate = fenced.group(1)
    start = candidate.find("[")
    end = candidate.rfind("]")
    if start >= 0 and end > start:
        candidate = candidate[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, list):
        raise ValueError("Gemini output did not contain a transaction array")
    return parsed


def _normalize_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _normalize_amount(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    negative_parens = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"[^\d\.\-]", "", raw)
    if not cleaned:
        return None
    try:
        out = Decimal(cleaned).quantize(Decimal("0.01"))
        return -abs(out) if negative_parens else out
    except (InvalidOperation, ValueError):
        return None


def _infer_expense_type(raw_type: Any, description: str, amount: Decimal) -> str:
    t = str(raw_type or "").strip().upper()
    if t in {"INCOME", "EXPENSE"}:
        return t
    if amount < 0:
        return "EXPENSE"
    income_keywords = (
        "SALARY",
        "PAYROLL",
        "REFUND",
        "INTEREST",
        "DIVIDEND",
        "CREDIT",
    )
    if any(k in description.upper() for k in income_keywords):
        return "INCOME"
    return "EXPENSE"


def _extract_pdf_rows_fallback(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        parsed = _parse_pdf_line(line)
        if not parsed:
            continue
        key = (
            str(parsed.get("date")),
            str(parsed.get("amount")),
            str(parsed.get("description")),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(parsed)
    return rows


def _parse_pdf_line(line: str) -> dict[str, Any] | None:
    date_patterns = (
        r"^(\d{4}-\d{2}-\d{2})\s+(.+)$",
        r"^(\d{2}/\d{2}/\d{4})\s+(.+)$",
        r"^(\d{2}/\d{2}/\d{2})\s+(.+)$",
        r"^(\d{2}-\d{2}-\d{4})\s+(.+)$",
    )
    rest: str | None = None
    tx_date: str | None = None
    for pattern in date_patterns:
        m = re.match(pattern, line)
        if m:
            tx_date = _normalize_date(m.group(1))
            rest = m.group(2).strip()
            break
    if not tx_date or not rest:
        return None

    amount_matches = list(
        re.finditer(r"(?<!\w)\(?-?\$?\d[\d,]*(?:\.\d{2})?\)?(?!\w)", rest)
    )
    if not amount_matches:
        return None
    amount_match = amount_matches[-1]
    amount = _normalize_amount(amount_match.group(0))
    if amount is None:
        return None

    description = rest[: amount_match.start()].strip(" -\t")
    if len(description) < 2:
        return None

    return {
        "date": tx_date,
        "amount": float(abs(amount)),
        "description": description,
        "category_id": None,
        "expense_type": _infer_expense_type(None, description, amount),
        "currency": "USD",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_date(value: Any) -> date | None:
    """Parse a date string into a date object. Returns None if unparseable."""
    if value is None:
        return None
    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_float(value: Any) -> float | None:
    """Parse a numeric value. Returns None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
