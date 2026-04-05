"""
Universal bank statement normalization layer (issue #112).
Parses CSV exports from major banks into a standard FinMind format.
Detects: Chase, Bank of America, Wells Fargo, Citi, generic fallback.
"""
import csv, io, logging, re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger("finmind.normalizer")

# Standard output schema
STANDARD_FIELDS = ["date", "description", "amount", "type", "currency"]


def _parse_date(raw: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[,$\s]", "", str(raw).strip())
    try:
        return float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


def _detect_bank(headers: set) -> str:
    h = {h.lower() for h in headers}
    if {"transaction date", "post date", "category"} <= h: return "chase"
    if {"date", "description", "amount", "running bal."} <= h: return "bofa"
    if {"date", "description", "deposits", "withdrawals", "closing balance"} <= h: return "wells_fargo"
    if {"date", "description", "debit", "credit"} <= h: return "citi"
    return "generic"


def _normalize_row_chase(row: dict) -> Optional[dict]:
    amt = _parse_amount(row.get("amount", ""))
    d = _parse_date(row.get("transaction date", ""))
    if amt is None or d is None: return None
    return {"date": d.isoformat(), "description": row.get("description", "").strip(),
            "amount": abs(amt), "type": "EXPENSE" if amt < 0 else "INCOME", "currency": "USD"}


def _normalize_row_bofa(row: dict) -> Optional[dict]:
    amt = _parse_amount(row.get("amount", ""))
    d = _parse_date(row.get("date", ""))
    if amt is None or d is None: return None
    return {"date": d.isoformat(), "description": row.get("description", "").strip(),
            "amount": abs(amt), "type": "EXPENSE" if amt < 0 else "INCOME", "currency": "USD"}


def _normalize_row_citi(row: dict) -> Optional[dict]:
    debit = _parse_amount(row.get("debit", "") or "0") or 0
    credit = _parse_amount(row.get("credit", "") or "0") or 0
    d = _parse_date(row.get("date", ""))
    if d is None: return None
    amt = credit if credit else debit
    return {"date": d.isoformat(), "description": row.get("description", "").strip(),
            "amount": amt, "type": "INCOME" if credit else "EXPENSE", "currency": "USD"}


def _normalize_row_generic(row: dict, headers: list) -> Optional[dict]:
    date_col = next((h for h in headers if "date" in h.lower()), None)
    amt_col = next((h for h in headers if "amount" in h.lower()), None)
    desc_col = next((h for h in headers if any(k in h.lower() for k in ["desc","narr","memo","note"])), None)
    if not date_col or not amt_col: return None
    amt = _parse_amount(row.get(amt_col, ""))
    d = _parse_date(row.get(date_col, ""))
    if amt is None or d is None: return None
    return {"date": d.isoformat(), "description": (row.get(desc_col, "") if desc_col else "").strip(),
            "amount": abs(amt), "type": "EXPENSE" if amt < 0 else "INCOME", "currency": "USD"}


def normalize_statement(raw_csv: str) -> dict:
    reader = csv.DictReader(io.StringIO(raw_csv.strip()))
    headers = list(reader.fieldnames or [])
    bank = _detect_bank(set(headers))
    normalizers = {"chase": _normalize_row_chase, "bofa": _normalize_row_bofa,
                   "citi": _normalize_row_citi}
    rows, errors = [], []
    for i, row in enumerate(reader, 2):
        r = row  # lowercase keys
        fn = normalizers.get(bank)
        result = fn(r) if fn else _normalize_row_generic(r, headers)
        if result: rows.append(result)
        else: errors.append(f"Row {i}: could not parse")
    return {"bank_detected": bank, "rows": rows, "row_count": len(rows),
            "errors": errors, "headers_found": headers}
