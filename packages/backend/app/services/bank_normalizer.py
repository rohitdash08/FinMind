"""
Universal bank statement normalization layer (#112).

Provides a unified normalization pipeline that can process statements from
diverse formats and bank-specific quirks, converting them into FinMind's
canonical expense schema.

Builds on top of the existing expense_import helpers and adds:
- Bank-profile auto-detection (Chase, HDFC, Axis, generic CSV/OFX/QIF)
- OFX/QFX (Open Financial Exchange) parsing
- QIF (Quicken Interchange Format) parsing
- Multi-currency normalisation
- Deduplication fingerprinting
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .expense_import import (
    _normalize_amount,
    _normalize_date,
    _infer_expense_type,
    normalize_import_rows,
)


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def normalize_statement(
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> dict[str, Any]:
    """
    Parse and normalise a bank statement from any supported format.

    Returns a dict with:
    - ``transactions``: list of normalised expense-like dicts
    - ``format_detected``: the detected format string
    - ``bank_profile``: detected bank name (if recognisable), else ``"generic"``
    - ``total_transactions``: count
    - ``duplicate_fingerprints``: list of SHA-256 fingerprints for dedup
    """
    name = (filename or "").lower()
    ctype = (content_type or "").lower()

    raw_rows: list[dict[str, Any]]
    fmt = "unknown"
    bank = "generic"

    if name.endswith(".ofx") or name.endswith(".qfx") or "ofx" in ctype:
        raw_rows = _parse_ofx(data)
        fmt = "OFX/QFX"
    elif name.endswith(".qif") or "qif" in ctype:
        raw_rows = _parse_qif(data)
        fmt = "QIF"
    elif name.endswith(".csv") or "csv" in ctype:
        raw_rows, bank = _parse_csv_with_profile(data)
        fmt = "CSV"
    else:
        raise ValueError(
            "Unsupported format. Accepted: .csv, .ofx, .qfx, .qif"
        )

    transactions = normalize_import_rows(raw_rows)
    fingerprints = [_fingerprint(t) for t in transactions]

    return {
        "transactions": transactions,
        "format_detected": fmt,
        "bank_profile": bank,
        "total_transactions": len(transactions),
        "duplicate_fingerprints": fingerprints,
    }


# ---------------------------------------------------------------------------
# OFX / QFX parser
# ---------------------------------------------------------------------------

def _parse_ofx(data: bytes) -> list[dict[str, Any]]:
    """Parse OFX/QFX (SGML or XML variant) and return raw row dicts."""
    text = data.decode("utf-8", errors="ignore")
    rows: list[dict[str, Any]] = []

    # OFX SGML format: each transaction is a block between <STMTTRN> tags
    # (or <BANKTRANLIST> children in XML variant)
    tx_blocks = re.findall(
        r"<STMTTRN>(.*?)</STMTTRN>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not tx_blocks:
        # Try the flat SGML header style where tags are not closed
        tx_blocks = re.findall(
            r"<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>|$)",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    for block in tx_blocks:
        def _tag(name: str) -> str | None:
            m = re.search(rf"<{name}>\s*([^\n<]+)", block, re.IGNORECASE)
            return m.group(1).strip() if m else None

        dtposted = _tag("DTPOSTED") or _tag("DTUSER") or ""
        # OFX date: YYYYMMDDHHMMSS[.xxx[GMT±HH:MM]]
        dt_str = dtposted[:8] if dtposted else ""
        parsed_date = None
        if dt_str:
            try:
                parsed_date = datetime.strptime(dt_str, "%Y%m%d").date().isoformat()
            except ValueError:
                pass

        amount_raw = _tag("TRNAMT") or ""
        memo = _tag("MEMO") or _tag("NAME") or ""
        currency = _tag("CURSYM") or _tag("CURRENCY") or "USD"

        if parsed_date and amount_raw:
            rows.append(
                {
                    "date": parsed_date,
                    "amount": amount_raw,
                    "description": memo,
                    "currency": currency,
                }
            )

    return rows


# ---------------------------------------------------------------------------
# QIF parser
# ---------------------------------------------------------------------------

def _parse_qif(data: bytes) -> list[dict[str, Any]]:
    """Parse Quicken Interchange Format (QIF) file."""
    text = data.decode("utf-8", errors="ignore")
    rows: list[dict[str, Any]] = []

    current: dict[str, str] = {}
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("!"):
            continue
        tag, value = line[0], line[1:].strip()

        if tag == "^":
            # End of record
            dt = _qif_date(current.get("D", ""))
            amt = current.get("T", "") or current.get("U", "")
            desc = current.get("P", "") or current.get("M", "")
            if dt and amt and desc:
                rows.append(
                    {
                        "date": dt,
                        "amount": amt.replace(",", "").replace(" ", ""),
                        "description": desc,
                        "currency": "USD",
                    }
                )
            current = {}
        elif tag in ("D", "T", "U", "P", "M", "N", "L", "C", "A"):
            current[tag] = value

    return rows


def _qif_date(raw: str) -> str | None:
    """Convert QIF date formats to ISO."""
    # Common QIF formats: MM/DD'YY, MM/DD/YYYY, D/M/YY, DD-MM-YYYY
    raw = raw.strip().replace("'", "/")
    for fmt in (
        "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y",
        "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# CSV parser with bank-profile auto-detection
# ---------------------------------------------------------------------------

_BANK_PROFILES: list[tuple[str, list[str], dict[str, str]]] = [
    # (bank_name, header_signature_columns, column_map)
    (
        "Chase",
        ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount"],
        {
            "date": "Transaction Date",
            "amount": "Amount",
            "description": "Description",
            "expense_type": "Type",
        },
    ),
    (
        "HDFC",
        ["Date", "Narration", "Value Dat", "Debit Amount", "Credit Amount"],
        {
            "date": "Date",
            "description": "Narration",
            "_debit": "Debit Amount",
            "_credit": "Credit Amount",
        },
    ),
    (
        "Axis",
        ["Tran Date", "PARTICULARS", "DR", "CR", "BAL"],
        {
            "date": "Tran Date",
            "description": "PARTICULARS",
            "_debit": "DR",
            "_credit": "CR",
        },
    ),
]


def _parse_csv_with_profile(data: bytes) -> tuple[list[dict[str, Any]], str]:
    """Parse CSV and try to auto-detect the bank profile."""
    import csv, io

    text = data.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [f.strip() for f in (reader.fieldnames or [])]

    detected_bank = "generic"
    col_map: dict[str, str] = {}

    for bank_name, signature, mapping in _BANK_PROFILES:
        if all(any(s.lower() in f.lower() for f in fieldnames) for s in signature[:3]):
            detected_bank = bank_name
            col_map = mapping
            break

    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        row = {k.strip(): v.strip() for k, v in raw_row.items() if k}

        if col_map:
            date_val = row.get(col_map.get("date", ""), "")
            desc = row.get(col_map.get("description", ""), "")
            expense_type_raw = row.get(col_map.get("expense_type", ""), "")

            # Handle debit/credit split columns (HDFC, Axis)
            if "_debit" in col_map and "_credit" in col_map:
                debit = row.get(col_map["_debit"], "").replace(",", "").strip()
                credit = row.get(col_map["_credit"], "").replace(",", "").strip()
                if debit and _to_decimal(debit) is not None:
                    amt = str(_to_decimal(debit))
                    expense_type_raw = "EXPENSE"
                elif credit and _to_decimal(credit) is not None:
                    amt = str(_to_decimal(credit))
                    expense_type_raw = "INCOME"
                else:
                    continue
            else:
                amt = row.get(col_map.get("amount", ""), "")
        else:
            # Generic fallback: best-guess column names
            date_val = (
                row.get("date") or row.get("Date") or row.get("Transaction Date") or ""
            )
            amt = row.get("amount") or row.get("Amount") or ""
            desc = (
                row.get("description")
                or row.get("Description")
                or row.get("Narration")
                or row.get("notes")
                or ""
            )
            expense_type_raw = row.get("type") or row.get("Type") or ""

        if not date_val or not amt or not desc:
            continue

        rows.append(
            {
                "date": date_val,
                "amount": amt,
                "description": desc,
                "expense_type": expense_type_raw,
                "currency": row.get("Currency") or row.get("currency") or "USD",
            }
        )

    return rows, detected_bank


def _to_decimal(value: str) -> Decimal | None:
    try:
        cleaned = re.sub(r"[^\d\.\-]", "", value)
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None


# ---------------------------------------------------------------------------
# Deduplication fingerprint
# ---------------------------------------------------------------------------

def _fingerprint(tx: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 fingerprint for a normalised transaction."""
    key = f"{tx.get('date')}|{tx.get('amount')}|{tx.get('description', '')[:50]}"
    return hashlib.sha256(key.encode()).hexdigest()
