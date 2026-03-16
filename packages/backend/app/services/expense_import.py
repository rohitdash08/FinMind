import csv
import io
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


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
# Validation & preview improvements (issue #115)
# ---------------------------------------------------------------------------

_MAX_REASONABLE_AMOUNT = Decimal("1_000_000")
_MIN_REASONABLE_AMOUNT = Decimal("0.01")
_FAR_FUTURE_DAYS = 7       # days ahead considered suspicious
_OLD_DATE_YEARS = 10       # years back considered suspicious


def validate_import_rows(
    raw_rows: list[dict[str, Any]],
    *,
    existing_descriptions: set[str] | None = None,
    existing_amounts: dict[str, list[Decimal]] | None = None,
    valid_category_ids: set[int] | None = None,
) -> dict[str, Any]:
    """
    Validate a list of raw import rows, enriching each with:
      - ``status``: "valid" | "warning" | "invalid"
      - ``warnings``: list of human-readable warning strings
      - ``corrections``: list of {field, original, corrected} dicts
      - ``normalized``: the cleaned row (None if invalid)

    Parameters
    ----------
    raw_rows : list[dict]
        Raw rows as returned by extract_transactions_from_statement.
    existing_descriptions : set[str], optional
        Set of (lower-cased description, date) tuples for duplicate detection.
    existing_amounts : dict[str, list[Decimal]], optional
        {YYYY-MM: [amounts]} for statistical outlier detection.
    valid_category_ids : set[int], optional
        Set of the user's valid category IDs; unknown IDs generate a warning.

    Returns
    -------
    dict with keys:
        rows         – list of per-row validation dicts
        summary      – counts (total, valid, warnings, invalid, duplicates)
    """
    today = date.today()
    far_future = date(today.year, today.month, today.day)
    old_cutoff = date(today.year - _OLD_DATE_YEARS, today.month, today.day)

    validated: list[dict[str, Any]] = []
    counts = {"total": 0, "valid": 0, "warnings": 0, "invalid": 0, "duplicates": 0}

    for idx, raw in enumerate(raw_rows):
        counts["total"] += 1
        row_warnings: list[str] = []
        corrections: list[dict[str, str]] = []

        # --- date ---
        raw_date = raw.get("date")
        norm_date = _normalize_date(raw_date)
        if norm_date is None:
            validated.append({
                "row_index": idx,
                "status": "invalid",
                "warnings": [f"Cannot parse date: {raw_date!r}"],
                "corrections": [],
                "normalized": None,
                "raw": raw,
            })
            counts["invalid"] += 1
            continue
        try:
            parsed_date = date.fromisoformat(norm_date)
        except ValueError:
            parsed_date = None

        if norm_date != str(raw_date or "").strip():
            corrections.append({
                "field": "date",
                "original": str(raw_date),
                "corrected": norm_date,
            })

        if parsed_date:
            if parsed_date > today:
                row_warnings.append(
                    f"Date {norm_date} is in the future"
                )
            elif parsed_date < old_cutoff:
                row_warnings.append(
                    f"Date {norm_date} is more than {_OLD_DATE_YEARS} years old"
                )

        # --- amount ---
        raw_amount = raw.get("amount")
        norm_amount = _normalize_amount(raw_amount)
        if norm_amount is None:
            validated.append({
                "row_index": idx,
                "status": "invalid",
                "warnings": [f"Cannot parse amount: {raw_amount!r}"],
                "corrections": [],
                "normalized": None,
                "raw": raw,
            })
            counts["invalid"] += 1
            continue

        abs_amount = abs(norm_amount)
        if abs_amount > _MAX_REASONABLE_AMOUNT:
            row_warnings.append(
                f"Amount {abs_amount} exceeds reasonable threshold "
                f"({_MAX_REASONABLE_AMOUNT})"
            )
        if abs_amount < _MIN_REASONABLE_AMOUNT:
            row_warnings.append(f"Amount {abs_amount} is below minimum 0.01")

        if str(raw_amount or "").strip() != str(float(abs_amount)):
            corrections.append({
                "field": "amount",
                "original": str(raw_amount),
                "corrected": str(float(abs_amount)),
            })

        # --- description ---
        raw_desc = raw.get("description") or ""
        norm_desc = str(raw_desc).strip()[:500]
        if not norm_desc:
            validated.append({
                "row_index": idx,
                "status": "invalid",
                "warnings": ["Description is empty"],
                "corrections": [],
                "normalized": None,
                "raw": raw,
            })
            counts["invalid"] += 1
            continue

        if len(str(raw_desc)) > 500:
            corrections.append({
                "field": "description",
                "original": f"{str(raw_desc)[:30]}… ({len(str(raw_desc))} chars)",
                "corrected": f"Truncated to 500 chars",
            })

        # --- category ---
        raw_cat = raw.get("category_id")
        category_id: int | None = None
        if raw_cat not in (None, "", "null"):
            try:
                category_id = int(raw_cat)
            except (TypeError, ValueError):
                row_warnings.append(
                    f"category_id {raw_cat!r} is not a valid integer; ignored"
                )
                corrections.append({
                    "field": "category_id",
                    "original": str(raw_cat),
                    "corrected": "null",
                })
        if category_id is not None and valid_category_ids is not None:
            if category_id not in valid_category_ids:
                row_warnings.append(
                    f"category_id {category_id} does not exist; will be left unset"
                )
                corrections.append({
                    "field": "category_id",
                    "original": str(category_id),
                    "corrected": "null",
                })
                category_id = None

        if category_id is None and valid_category_ids is not None:
            row_warnings.append("No category assigned; transaction will be uncategorised")

        # --- duplicate detection ---
        dup_key = (norm_desc.lower(), norm_date)
        if existing_descriptions and dup_key in existing_descriptions:
            row_warnings.append(
                f"Possible duplicate: '{norm_desc}' on {norm_date} already exists"
            )
            counts["duplicates"] += 1

        # --- expense type ---
        raw_type = raw.get("expense_type")
        norm_type = _infer_expense_type(raw_type, norm_desc, norm_amount)
        if str(raw_type or "").strip().upper() not in ("INCOME", "EXPENSE", ""):
            corrections.append({
                "field": "expense_type",
                "original": str(raw_type),
                "corrected": norm_type,
            })

        # --- currency ---
        raw_currency = str(raw.get("currency") or "USD").strip()[:10] or "USD"

        # --- build normalized row ---
        normalized = {
            "date": norm_date,
            "amount": float(abs_amount),
            "description": norm_desc,
            "category_id": category_id,
            "expense_type": norm_type,
            "currency": raw_currency,
        }

        status = "valid" if not row_warnings else "warning"
        counts["valid" if status == "valid" else "warnings"] += 1

        validated.append({
            "row_index": idx,
            "status": status,
            "warnings": row_warnings,
            "corrections": corrections,
            "normalized": normalized,
            "raw": raw,
        })

    return {
        "rows": validated,
        "summary": counts,
    }

