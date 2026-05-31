import csv
import io
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.import_validation")

CUSTOM_FORMATS = {
    "chase": {"date": "%m/%d/%Y", "date_col": "Transaction Date", "amount_col": "Amount", "desc_col": "Description"},
    "boa": {"date": "%m/%d/%Y", "date_col": "Date", "amount_col": "Amount", "desc_col": "Payee"},
    "wells_fargo": {"date": "%m/%d/%Y", "date_col": "Date", "amount_col": "Amount", "desc_col": "Description"},
    "citi": {"date": "%m/%d/%Y", "date_col": "Date", "amount_col": "Amount", "desc_col": "Description"},
    "amex": {"date": "%m/%d/%Y", "date_col": "Date", "amount_col": "Amount", "desc_col": "Description"},
    "hdfc": {"date": "%d/%m/%Y", "date_col": "Date", "amount_col": "Withdrawal", "desc_col": "Narration"},
}


def validate_csv_row(row: dict[str, str], row_index: int) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    parsed: dict[str, Any] = {}

    raw_date = row.get("date") or row.get("Date") or row.get("spent_at") or ""
    if raw_date:
        parsed_date = _normalize_date(raw_date.strip())
        if parsed_date:
            parsed["date"] = parsed_date
        else:
            errors.append(f"row {row_index}: invalid date '{raw_date}'")
    else:
        errors.append(f"row {row_index}: missing date")

    raw_amount = row.get("amount") or row.get("Amount") or row.get("Withdrawal") or row.get("Deposit") or ""
    if raw_amount:
        parsed_amount = _normalize_amount(raw_amount.strip())
        if parsed_amount is not None:
            parsed["amount"] = float(abs(parsed_amount))
        else:
            errors.append(f"row {row_index}: invalid amount '{raw_amount}'")
    else:
        errors.append(f"row {row_index}: missing amount")

    raw_desc = row.get("description") or row.get("Description") or row.get("Payee") or row.get("Narration") or row.get("notes") or row.get("Memo") or row.get("memo") or ""
    desc = raw_desc.strip()
    if desc:
        parsed["description"] = desc[:500]
    else:
        errors.append(f"row {row_index}: missing description")

    raw_type = row.get("expense_type") or row.get("Type") or row.get("Transaction Type") or ""
    if raw_type:
        t = raw_type.strip().upper()
        if t in ("DEBIT", "WITHDRAWAL", "PAYMENT", "EXPENSE", "SALE"):
            parsed["expense_type"] = "EXPENSE"
        elif t in ("CREDIT", "DEPOSIT", "REFUND", "INCOME"):
            parsed["expense_type"] = "INCOME"

    return {
        "row_index": row_index,
        "original": dict(row),
        "parsed": parsed,
        "errors": errors,
        "warnings": warnings,
        "valid": len(errors) == 0,
    }


def validate_csv_data(
    content: bytes,
    bank_format: str | None = None,
) -> dict[str, Any]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if bank_format and bank_format in CUSTOM_FORMATS:
        fmt = CUSTOM_FORMATS[bank_format]
        mapped = []
        for row in rows:
            mapped.append({
                "date": row.get(fmt["date_col"], ""),
                "amount": row.get(fmt["amount_col"], ""),
                "description": row.get(fmt["desc_col"], ""),
            })
        rows = mapped

    results = [validate_csv_row(row, i) for i, row in enumerate(rows)]
    valid_count = sum(1 for r in results if r["valid"])
    error_count = sum(1 for r in results if not r["valid"])
    return {
        "total": len(results),
        "valid": valid_count,
        "with_errors": error_count,
        "rows": results,
    }


def detect_bank_format(headers: list[str]) -> str | None:
    h = set(h.lower() for h in headers)
    if "transaction date" in h and "amount" in h and "description" in h:
        return "chase"
    if "narration" in h and "withdrawal" in h:
        return "hdfc"
    if "payee" in h and "amount" in h:
        return "boa"
    return None


def _normalize_date(value: str) -> str | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_amount(value: str) -> Decimal | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d\.\-]", "", value.replace(",", ""))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
