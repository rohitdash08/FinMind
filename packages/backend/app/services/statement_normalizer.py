"""Universal bank statement normalization layer.

Parses and normalizes bank statements from multiple formats (CSV variants,
OFX/QFX) into a unified transaction schema for import.
"""

import csv
import io
import re
from datetime import datetime, date
from dataclasses import dataclass, asdict


@dataclass
class NormalizedTransaction:
    date: str  # ISO format
    amount: float
    description: str
    raw_description: str
    transaction_type: str  # debit / credit
    balance: float | None = None
    reference: str | None = None


# Common date formats across banks
DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
    "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y",
    "%m-%d-%Y", "%d.%m.%Y",
]


def normalize_statement(content: str, format_hint: str | None = None) -> dict:
    """Parse a bank statement and return normalized transactions.

    Args:
        content: Raw file content (CSV or OFX string)
        format_hint: Optional hint ('csv', 'ofx', 'qfx')

    Returns:
        Dict with transactions list, stats, and any warnings.
    """
    fmt = format_hint or _detect_format(content)

    if fmt in ("ofx", "qfx"):
        txns, warnings = _parse_ofx(content)
    else:
        txns, warnings = _parse_csv(content)

    return {
        "format_detected": fmt,
        "total_transactions": len(txns),
        "transactions": [asdict(t) for t in txns],
        "summary": _summarize(txns),
        "warnings": warnings,
    }


def _detect_format(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("OFXHEADER") or "<OFX>" in stripped[:500]:
        return "ofx"
    return "csv"


def _parse_date(value: str) -> str | None:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    # OFX date format: YYYYMMDD or YYYYMMDDHHMMSS
    if re.match(r"^\d{8}", value):
        try:
            return datetime.strptime(value[:8], "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    return None


def _clean_description(desc: str) -> str:
    desc = re.sub(r"\s+", " ", desc.strip())
    desc = re.sub(r"\b\d{4}\*+\d{4}\b", "", desc)  # mask card numbers
    desc = re.sub(r"\s{2,}", " ", desc).strip()
    return desc


def _parse_amount(value: str) -> float:
    value = value.strip().replace(",", "").replace(" ", "")
    value = re.sub(r"[^\d.\-+]", "", value)
    return float(value) if value else 0.0


def _detect_csv_columns(headers: list[str]) -> dict:
    """Map CSV headers to our expected fields."""
    mapping = {}
    header_lower = [h.lower().strip() for h in headers]

    date_keys = ["date", "transaction date", "posting date", "value date", "txn date"]
    amount_keys = ["amount", "transaction amount", "debit/credit", "sum"]
    desc_keys = ["description", "narrative", "details", "memo", "particulars", "transaction description"]
    balance_keys = ["balance", "running balance", "closing balance"]
    ref_keys = ["reference", "ref", "transaction ref", "cheque no"]
    debit_keys = ["debit", "withdrawal", "dr"]
    credit_keys = ["credit", "deposit", "cr"]

    for i, h in enumerate(header_lower):
        if h in date_keys:
            mapping["date"] = i
        elif h in amount_keys:
            mapping["amount"] = i
        elif h in desc_keys:
            mapping["description"] = i
        elif h in balance_keys:
            mapping["balance"] = i
        elif h in ref_keys:
            mapping["reference"] = i
        elif h in debit_keys:
            mapping["debit"] = i
        elif h in credit_keys:
            mapping["credit"] = i

    return mapping


def _parse_csv(content: str) -> tuple[list[NormalizedTransaction], list[str]]:
    warnings = []
    txns = []

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if len(rows) < 2:
        return [], ["File has fewer than 2 rows"]

    mapping = _detect_csv_columns(rows[0])
    if "date" not in mapping:
        warnings.append("Could not detect date column")
        return [], warnings

    has_split = "debit" in mapping and "credit" in mapping
    if "amount" not in mapping and not has_split:
        warnings.append("Could not detect amount column")
        return [], warnings

    for row_idx, row in enumerate(rows[1:], start=2):
        try:
            if len(row) <= max(mapping.values()):
                continue

            parsed_date = _parse_date(row[mapping["date"]])
            if not parsed_date:
                warnings.append(f"Row {row_idx}: unparseable date '{row[mapping['date']]}'")
                continue

            if has_split:
                debit = _parse_amount(row[mapping["debit"]]) if row[mapping["debit"]].strip() else 0
                credit = _parse_amount(row[mapping["credit"]]) if row[mapping["credit"]].strip() else 0
                amount = credit - debit if credit else -debit
            else:
                amount = _parse_amount(row[mapping["amount"]])

            raw_desc = row[mapping.get("description", mapping.get("date"))]
            balance = _parse_amount(row[mapping["balance"]]) if "balance" in mapping and row[mapping["balance"]].strip() else None
            reference = row[mapping["reference"]].strip() if "reference" in mapping and len(row) > mapping["reference"] else None

            txns.append(NormalizedTransaction(
                date=parsed_date,
                amount=abs(amount),
                description=_clean_description(raw_desc),
                raw_description=raw_desc.strip(),
                transaction_type="credit" if amount >= 0 else "debit",
                balance=balance,
                reference=reference,
            ))
        except (IndexError, ValueError) as e:
            warnings.append(f"Row {row_idx}: {str(e)}")

    return txns, warnings


def _parse_ofx(content: str) -> tuple[list[NormalizedTransaction], list[str]]:
    """Simple OFX/QFX parser (SGML-style, no XML dependency)."""
    warnings = []
    txns = []

    # Extract STMTTRN blocks
    blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", content, re.DOTALL)
    if not blocks:
        # Try without closing tags (some OFX files)
        blocks = re.findall(r"<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>|$)", content, re.DOTALL)

    for block in blocks:
        try:
            dt_match = re.search(r"<DTPOSTED>(\d{8,14})", block)
            amt_match = re.search(r"<TRNAMT>([\-\d.]+)", block)
            name_match = re.search(r"<NAME>(.+?)(?:\n|<)", block)
            memo_match = re.search(r"<MEMO>(.+?)(?:\n|<)", block)
            ref_match = re.search(r"<FITID>(.+?)(?:\n|<)", block)

            if not dt_match or not amt_match:
                continue

            parsed_date = _parse_date(dt_match.group(1))
            amount = float(amt_match.group(1))
            desc = (name_match.group(1) if name_match else memo_match.group(1) if memo_match else "Unknown").strip()

            txns.append(NormalizedTransaction(
                date=parsed_date or "unknown",
                amount=abs(amount),
                description=_clean_description(desc),
                raw_description=desc,
                transaction_type="credit" if amount >= 0 else "debit",
                reference=ref_match.group(1).strip() if ref_match else None,
            ))
        except Exception as e:
            warnings.append(f"OFX block parse error: {str(e)}")

    return txns, warnings


def _summarize(txns: list[NormalizedTransaction]) -> dict:
    if not txns:
        return {"total_debits": 0, "total_credits": 0, "net": 0, "date_range": None}

    debits = sum(t.amount for t in txns if t.transaction_type == "debit")
    credits = sum(t.amount for t in txns if t.transaction_type == "credit")
    dates = [t.date for t in txns if t.date != "unknown"]

    return {
        "total_debits": round(debits, 2),
        "total_credits": round(credits, 2),
        "net": round(credits - debits, 2),
        "date_range": {"start": min(dates), "end": max(dates)} if dates else None,
    }
