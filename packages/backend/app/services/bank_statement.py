"""Universal bank statement normalization layer.

Normalizes diverse bank statement formats (CSV, OFX/QFX, PDF text)
into a unified transaction schema. Supports multiple bank formats
with extensible parser registry.
"""

import csv
import io
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional


# ── Unified Transaction Schema ────────────────────────────────────

class NormalizedTransaction:
    """Unified transaction representation."""

    def __init__(
        self,
        date: date,
        amount: float,
        description: str,
        transaction_type: str = "debit",  # debit | credit
        reference: str = "",
        balance: Optional[float] = None,
        category_hint: str = "",
        raw_data: Optional[dict] = None,
    ):
        self.date = date
        self.amount = abs(amount)
        self.description = description.strip()
        self.transaction_type = transaction_type
        self.reference = reference.strip()
        self.balance = balance
        self.category_hint = category_hint
        self.raw_data = raw_data or {}

    def to_dict(self) -> dict:
        return {
            "date": str(self.date),
            "amount": self.amount,
            "description": self.description,
            "transaction_type": self.transaction_type,
            "reference": self.reference,
            "balance": self.balance,
            "category_hint": self.category_hint,
        }


# ── Date Parsing ──────────────────────────────────────────────────

DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%m/%d/%y",
    "%d/%m/%y",
]


def parse_date(value: str) -> Optional[date]:
    """Try multiple date formats."""
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: str) -> Optional[float]:
    """Parse an amount string, handling currency symbols and formats."""
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,\-]", "", value.strip())
    # Handle European format (1.234,56 → 1234.56)
    if re.match(r"^-?\d{1,3}(\.\d{3})*(,\d{2})?$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


# ── Column Detection ──────────────────────────────────────────────

COLUMN_PATTERNS = {
    "date": [
        r"^date$", r"^transaction.?date$", r"^txn.?date$", r"^posting.?date$",
        r"^value.?date$", r"^trans.?date$", r"^booked$", r"^when$",
    ],
    "debit": [r"^debit$", r"^withdrawal$", r"^debit.?amount$", r"^dr$"],
    "credit": [r"^credit$", r"^deposit$", r"^credit.?amount$", r"^cr$"],
    "amount": [
        r"^amount$", r"^transaction.?amount$",
        r"^value$", r"^sum$", r"^total$",
    ],
    "description": [
        r"^description$", r"^narrative$", r"^details$", r"^particulars$",
        r"^memo$", r"^notes$", r"^payee$", r"^merchant$", r"^transaction.?details$",
    ],
    "reference": [
        r"^reference$", r"^ref$", r"^txn.?ref$", r"^check.?no$",
        r"^cheque.?no$", r"^transaction.?id$",
    ],
    "balance": [
        r"^balance$", r"^running.?balance$", r"^closing.?balance$",
        r"^available.?balance$",
    ],
}


def detect_columns(headers: list[str]) -> dict:
    """Auto-detect column mapping from headers."""
    mapping = {}
    for header in headers:
        normalized = header.strip().lower().replace(" ", "_")
        for field, patterns in COLUMN_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, normalized):
                    mapping[header] = field
                    break
            if header in mapping:
                break
    return mapping


# ── Parsers ───────────────────────────────────────────────────────


def parse_csv_statement(
    content: str,
    column_mapping: Optional[dict] = None,
    date_format: Optional[str] = None,
) -> dict:
    """Parse a CSV bank statement into normalized transactions.

    Args:
        content: Raw CSV content
        column_mapping: Optional manual column mapping {header: field}
        date_format: Optional specific date format string

    Returns:
        {
            "transactions": [...],
            "detected_columns": {...},
            "total_rows": int,
            "parsed_rows": int,
            "skipped_rows": int,
            "warnings": [...],
            "summary": {...}
        }
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return _empty_result("No headers found in CSV")

    headers = list(reader.fieldnames)
    mapping = column_mapping or detect_columns(headers)

    # Find which mapped field each header maps to
    reverse_mapping = {}
    for header, field in mapping.items():
        if field not in reverse_mapping:
            reverse_mapping[field] = header

    if "date" not in reverse_mapping:
        return _empty_result("No date column detected", mapping)
    if "amount" not in reverse_mapping and "debit" not in reverse_mapping:
        return _empty_result("No amount/debit column detected", mapping)

    transactions = []
    warnings = []
    skipped = 0

    for idx, row in enumerate(reader, 1):
        # Parse date
        date_col = reverse_mapping.get("date", "")
        date_str = row.get(date_col, "").strip()
        if not date_str:
            skipped += 1
            warnings.append(f"Row {idx}: Missing date — skipped")
            continue

        if date_format:
            try:
                txn_date = datetime.strptime(date_str, date_format).date()
            except ValueError:
                txn_date = parse_date(date_str)
        else:
            txn_date = parse_date(date_str)

        if not txn_date:
            skipped += 1
            warnings.append(f"Row {idx}: Unrecognized date '{date_str}' — skipped")
            continue

        # Parse amount
        amount = None
        txn_type = "debit"

        if "amount" in reverse_mapping:
            amount_str = row.get(reverse_mapping["amount"], "")
            amount = parse_amount(amount_str)
            if amount is not None and amount < 0:
                txn_type = "debit"
                amount = abs(amount)
            elif amount is not None:
                txn_type = "credit"
        elif "debit" in reverse_mapping or "credit" in reverse_mapping:
            debit_str = row.get(reverse_mapping.get("debit", ""), "")
            credit_str = row.get(reverse_mapping.get("credit", ""), "")
            debit_amt = parse_amount(debit_str)
            credit_amt = parse_amount(credit_str)
            if debit_amt and debit_amt > 0:
                amount = debit_amt
                txn_type = "debit"
            elif credit_amt and credit_amt > 0:
                amount = credit_amt
                txn_type = "credit"

        if amount is None:
            skipped += 1
            warnings.append(f"Row {idx}: Cannot parse amount — skipped")
            continue

        # Parse description
        desc_col = reverse_mapping.get("description", "")
        description = row.get(desc_col, "").strip() if desc_col else ""
        if not description:
            # Try to build from available non-mapped fields
            for h in headers:
                if h not in mapping and row.get(h, "").strip():
                    description = row[h].strip()
                    break

        # Parse reference
        ref_col = reverse_mapping.get("reference", "")
        reference = row.get(ref_col, "").strip() if ref_col else ""

        # Parse balance
        bal_col = reverse_mapping.get("balance", "")
        balance = parse_amount(row.get(bal_col, "")) if bal_col else None

        txn = NormalizedTransaction(
            date=txn_date,
            amount=amount,
            description=description,
            transaction_type=txn_type,
            reference=reference,
            balance=balance,
            raw_data=dict(row),
        )
        transactions.append(txn)

    return _build_result(transactions, mapping, skipped, warnings)


def parse_ofx_statement(content: str) -> dict:
    """Parse OFX/QFX bank statement content.

    Simplified OFX parser that extracts STMTTRN elements.
    """
    transactions = []
    warnings = []
    skipped = 0

    # Extract transaction blocks
    txn_blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", content, re.DOTALL | re.IGNORECASE)

    if not txn_blocks:
        # Try without closing tags (OFX 1.x / SGML-style)
        parts = re.split(r"<STMTTRN>", content, flags=re.IGNORECASE)
        if len(parts) > 1:
            txn_blocks = parts[1:]  # Skip first empty
        else:
            txn_blocks = []

    for idx, block in enumerate(txn_blocks, 1):
        # Extract fields via tag patterns
        def extract(tag):
            m = re.search(rf"<{tag}>\s*([^<\n]+)", block, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        # Date (YYYYMMDD format in OFX)
        date_str = extract("DTPOSTED")
        if not date_str:
            skipped += 1
            continue
        try:
            txn_date = datetime.strptime(date_str[:8], "%Y%m%d").date()
        except ValueError:
            txn_date = parse_date(date_str)
            if not txn_date:
                skipped += 1
                warnings.append(f"Transaction {idx}: Bad date '{date_str}'")
                continue

        # Amount
        amount_str = extract("TRNAMT")
        amount = parse_amount(amount_str)
        if amount is None:
            skipped += 1
            continue

        txn_type = "credit" if amount >= 0 else "debit"

        # Description
        name = extract("NAME")
        memo = extract("MEMO")
        description = name or memo

        # Reference
        fitid = extract("FITID")

        txn = NormalizedTransaction(
            date=txn_date,
            amount=abs(amount),
            description=description,
            transaction_type=txn_type,
            reference=fitid,
        )
        transactions.append(txn)

    return _build_result(transactions, {"format": "OFX/QFX"}, skipped, warnings)


def parse_text_statement(content: str) -> dict:
    """Parse plain text / PDF-extracted bank statement.

    Looks for lines with date + amount patterns.
    """
    transactions = []
    warnings = []
    skipped = 0
    lines = content.strip().split("\n")

    # Pattern: date ... description ... amount
    # Flexible: tries to find date at start and amount at end
    date_pattern = re.compile(
        r"^(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})"
    )
    amount_pattern = re.compile(
        r"([\-]?\d{1,3}(?:[,\.]\d{3})*(?:[,\.]\d{2}))\s*(?:(?:Dr|Cr|DR|CR))?\s*$"
    )

    for idx, line in enumerate(lines, 1):
        line = line.strip()
        if not line or len(line) < 10:
            continue

        date_match = date_pattern.match(line)
        amount_match = amount_pattern.search(line)

        if not date_match or not amount_match:
            continue

        txn_date = parse_date(date_match.group(1))
        if not txn_date:
            skipped += 1
            continue

        amount = parse_amount(amount_match.group(1))
        if amount is None:
            skipped += 1
            continue

        # Description is between date and amount
        desc_start = date_match.end()
        desc_end = amount_match.start()
        description = line[desc_start:desc_end].strip()

        # Check for Dr/Cr suffix
        txn_type = "debit"
        if re.search(r"(?:Cr|CR)\s*$", line):
            txn_type = "credit"

        txn = NormalizedTransaction(
            date=txn_date,
            amount=amount,
            description=description,
            transaction_type=txn_type,
        )
        transactions.append(txn)

    return _build_result(transactions, {"format": "text"}, skipped, warnings)


# ── Format Detection ──────────────────────────────────────────────


def detect_statement_format(content: str, filename: str = "") -> str:
    """Detect statement format."""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    if ext in ("ofx", "qfx"):
        return "ofx"
    if ext == "csv":
        return "csv"

    content_start = content.strip()[:500].upper()
    if "<OFX>" in content_start or "OFXHEADER" in content_start:
        return "ofx"
    if "," in content.split("\n")[0] and content.count(",") > 3:
        return "csv"
    return "text"


def normalize_statement(
    content: str,
    filename: str = "",
    file_format: str = "",
    column_mapping: Optional[dict] = None,
    date_format: Optional[str] = None,
) -> dict:
    """Main entry point: detect format and normalize statement.

    Returns unified result with normalized transactions.
    """
    fmt = file_format or detect_statement_format(content, filename)

    if fmt == "ofx":
        result = parse_ofx_statement(content)
    elif fmt == "csv":
        result = parse_csv_statement(content, column_mapping, date_format)
    else:
        result = parse_text_statement(content)

    result["detected_format"] = fmt
    return result


# ── Helpers ───────────────────────────────────────────────────────


def _empty_result(error: str, mapping: dict = None) -> dict:
    return {
        "transactions": [],
        "detected_columns": mapping or {},
        "total_rows": 0,
        "parsed_rows": 0,
        "skipped_rows": 0,
        "warnings": [],
        "errors": [error],
        "summary": {},
    }


def _build_result(
    transactions: list[NormalizedTransaction],
    mapping: dict,
    skipped: int,
    warnings: list,
) -> dict:
    txn_dicts = [t.to_dict() for t in transactions]

    debits = [t for t in transactions if t.transaction_type == "debit"]
    credits = [t for t in transactions if t.transaction_type == "credit"]

    summary = {}
    if transactions:
        summary = {
            "total_transactions": len(transactions),
            "total_debits": len(debits),
            "total_credits": len(credits),
            "total_debit_amount": round(sum(t.amount for t in debits), 2),
            "total_credit_amount": round(sum(t.amount for t in credits), 2),
            "date_range": {
                "earliest": str(min(t.date for t in transactions)),
                "latest": str(max(t.date for t in transactions)),
            },
            "unique_descriptions": len(set(t.description for t in transactions if t.description)),
        }

    return {
        "transactions": txn_dicts,
        "detected_columns": mapping,
        "total_rows": len(transactions) + skipped,
        "parsed_rows": len(transactions),
        "skipped_rows": skipped,
        "warnings": warnings,
        "errors": [],
        "summary": summary,
    }
