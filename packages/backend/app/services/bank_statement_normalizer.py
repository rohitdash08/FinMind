"""
Universal Bank Statement Normalization Layer (#112)
Normalizes diverse bank statement formats into a unified schema.
Supports: CSV columns (various headers), date formats, amount signs.
"""
import re
import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass, field
from typing import Any


# ── Unified Schema ────────────────────────────────────────────────────────────

@dataclass
class NormalizedTransaction:
    """Unified transaction schema for any bank statement format."""
    date: date
    description: str
    amount: Decimal          # Positive = credit/income, Negative = debit/expense
    transaction_type: str    # "EXPENSE" | "INCOME"
    raw_amount: str          # Original raw amount string
    raw_date: str            # Original raw date string
    category_hint: str = ""  # Guessed category from description
    reference: str = ""      # Transaction ID / reference if available
    balance: Decimal | None = None  # Running balance if present


@dataclass
class NormalizationResult:
    """Result of normalizing a bank statement."""
    transactions: list[NormalizedTransaction] = field(default_factory=list)
    total_rows: int = 0
    parsed_rows: int = 0
    skipped_rows: int = 0
    errors: list[str] = field(default_factory=list)
    detected_format: str = "unknown"
    currency_hint: str = ""


# ── Date Normalization ────────────────────────────────────────────────────────

DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%m/%d/%Y", "%m-%d-%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d %b %Y", "%d-%b-%Y", "%d %B %Y",
    "%b %d, %Y", "%B %d, %Y",
    "%d/%m/%y", "%m/%d/%y",
    "%Y%m%d",
]


def normalize_date(raw: str) -> date | None:
    """Try all known date formats and return a date object."""
    raw = raw.strip().strip('"').strip("'")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


# ── Amount Normalization ──────────────────────────────────────────────────────

def normalize_amount(raw: str, negate: bool = False) -> Decimal | None:
    """
    Normalize a raw amount string to a Decimal.
    Handles: commas as thousand separators, parentheses for negatives,
    currency symbols, CR/DR suffixes.
    """
    raw = raw.strip().strip('"').strip("'")
    if not raw or raw in ("-", "N/A", "n/a", "--"):
        return None

    # Remove currency symbols
    raw = re.sub(r"[£$€₹¥₩₦₽]", "", raw)

    # Handle CR/DR suffix
    is_credit = raw.upper().endswith("CR")
    is_debit = raw.upper().endswith("DR")
    raw = re.sub(r"\s*[CD]R$", "", raw, flags=re.IGNORECASE)

    # Handle parentheses as negative: (1,234.56) -> -1234.56
    is_paren_negative = raw.startswith("(") and raw.endswith(")")
    if is_paren_negative:
        raw = raw[1:-1]

    # Remove thousand separators (comma or dot used as separator)
    # European format: 1.234,56 -> 1234.56
    if re.search(r"\d\.\d{3},\d{2}$", raw):
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")

    try:
        amount = Decimal(raw.strip())
    except InvalidOperation:
        return None

    if is_paren_negative or is_debit:
        amount = -abs(amount)
    elif is_credit:
        amount = abs(amount)

    if negate:
        amount = -amount

    return amount


# ── Column Header Mapping ─────────────────────────────────────────────────────

# Maps normalized column names to possible CSV header variants
COLUMN_ALIASES = {
    "date": ["date", "transaction date", "txn date", "posting date", "value date",
             "transaction_date", "date posted", "dated", "settlement date"],
    "description": ["description", "narration", "particulars", "transaction description",
                    "details", "remarks", "payee", "merchant", "memo",
                    "transaction details", "transaction narration"],
    "amount": ["amount", "transaction amount", "txn amount", "net amount"],
    "debit": ["debit", "withdrawal", "withdrawals", "dr", "debit amount",
              "money out", "payment", "dr amount", "spent"],
    "credit": ["credit", "deposit", "deposits", "cr", "credit amount",
               "money in", "received", "cr amount"],
    "balance": ["balance", "running balance", "closing balance", "available balance"],
    "reference": ["reference", "ref", "reference no", "transaction id", "txn id",
                  "chq no", "cheque number", "ref no", "ref number"],
}


def _find_column(headers: list[str], key: str) -> int | None:
    """Find the index of a column by checking aliases."""
    aliases = COLUMN_ALIASES.get(key, [])
    for i, h in enumerate(headers):
        h_lower = h.lower().strip().strip('"')
        if h_lower in aliases or h_lower == key:
            return i
    return None


# ── Category Hinting ─────────────────────────────────────────────────────────

CATEGORY_HINTS = {
    "salary": "Income",
    "payroll": "Income",
    "dividend": "Income",
    "interest": "Income/Banking",
    "atm": "Cash Withdrawal",
    "uber": "Transport",
    "ola": "Transport",
    "petrol": "Transport",
    "fuel": "Transport",
    "zomato": "Food Delivery",
    "swiggy": "Food Delivery",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "netflix": "Entertainment",
    "spotify": "Entertainment",
    "rent": "Housing",
    "grocery": "Groceries",
    "supermarket": "Groceries",
    "pharmacy": "Medical",
    "hospital": "Medical",
    "insurance": "Insurance",
    "emi": "Loan EMI",
    "electricity": "Utilities",
    "water": "Utilities",
    "internet": "Utilities",
    "mobile": "Utilities",
}


def _guess_category(description: str) -> str:
    """Guess a category from the transaction description."""
    desc_lower = (description or "").lower()
    for kw, cat in CATEGORY_HINTS.items():
        if kw in desc_lower:
            return cat
    return ""


# ── Main Normalizer ───────────────────────────────────────────────────────────

def normalize_statement(
    content: str,
    file_format: str = "auto",
    delimiter: str = ",",
) -> NormalizationResult:
    """
    Normalize a bank statement CSV into the unified transaction schema.

    Args:
        content: Raw file content as string
        file_format: 'csv', 'tsv', or 'auto' (auto-detect)
        delimiter: Column separator (default: comma)

    Returns:
        NormalizationResult with normalized transactions and metadata
    """
    result = NormalizationResult()

    # Auto-detect or force delimiter
    if file_format == "tsv":
        delimiter = "\t"
    elif file_format == "auto":
        if "\t" in content[:500]:
            delimiter = "\t"
            file_format = "tsv"
        else:
            file_format = "csv"

    result.detected_format = file_format

    try:
        reader = csv.reader(io.StringIO(content.strip()), delimiter=delimiter)
        rows = list(reader)
    except Exception as e:
        result.errors.append(f"Failed to parse CSV: {e}")
        return result

    if not rows:
        result.errors.append("Empty file")
        return result

    # Find header row (first non-empty row)
    header_idx = 0
    for i, row in enumerate(rows):
        if any(cell.strip() for cell in row):
            header_idx = i
            break

    headers = [h.strip().strip('"') for h in rows[header_idx]]
    data_rows = rows[header_idx + 1:]
    result.total_rows = len(data_rows)

    # Map columns
    date_col = _find_column(headers, "date")
    desc_col = _find_column(headers, "description")
    amount_col = _find_column(headers, "amount")
    debit_col = _find_column(headers, "debit")
    credit_col = _find_column(headers, "credit")
    balance_col = _find_column(headers, "balance")
    ref_col = _find_column(headers, "reference")

    if date_col is None:
        result.errors.append("Could not find date column")
        return result

    if desc_col is None:
        result.errors.append("Could not find description column")
        return result

    if amount_col is None and debit_col is None and credit_col is None:
        result.errors.append("Could not find amount column(s)")
        return result

    # Parse each row
    for row_num, row in enumerate(data_rows, start=1):
        if len(row) <= max(
            date_col,
            desc_col,
            amount_col if amount_col is not None else 0,
            debit_col if debit_col is not None else 0,
        ):
            result.skipped_rows += 1
            continue

        raw_date = row[date_col] if date_col < len(row) else ""
        raw_desc = row[desc_col] if desc_col < len(row) else ""

        if not raw_date.strip() and not raw_desc.strip():
            result.skipped_rows += 1
            continue

        parsed_date = normalize_date(raw_date)
        if parsed_date is None:
            result.skipped_rows += 1
            result.errors.append(f"Row {row_num}: Cannot parse date '{raw_date}'")
            continue

        # Determine amount
        amount = None
        raw_amount = ""

        if amount_col is not None and amount_col < len(row):
            raw_amount = row[amount_col]
            amount = normalize_amount(raw_amount)
        elif debit_col is not None or credit_col is not None:
            raw_debit = row[debit_col].strip() if debit_col is not None and debit_col < len(row) else ""
            raw_credit = row[credit_col].strip() if credit_col is not None and credit_col < len(row) else ""

            if raw_debit and raw_debit not in ("0", "0.00", ""):
                raw_amount = raw_debit
                amount = normalize_amount(raw_debit)
                if amount is not None:
                    amount = -abs(amount)  # Debit = negative
            elif raw_credit and raw_credit not in ("0", "0.00", ""):
                raw_amount = raw_credit
                amount = normalize_amount(raw_credit)
                if amount is not None:
                    amount = abs(amount)  # Credit = positive

        if amount is None:
            result.skipped_rows += 1
            continue

        # Determine transaction type
        txn_type = "INCOME" if amount > 0 else "EXPENSE"

        # Balance
        balance = None
        if balance_col is not None and balance_col < len(row):
            balance = normalize_amount(row[balance_col])

        # Reference
        reference = row[ref_col].strip() if ref_col is not None and ref_col < len(row) else ""

        txn = NormalizedTransaction(
            date=parsed_date,
            description=raw_desc.strip().strip('"'),
            amount=amount,
            transaction_type=txn_type,
            raw_amount=raw_amount,
            raw_date=raw_date.strip(),
            category_hint=_guess_category(raw_desc),
            reference=reference,
            balance=balance,
        )
        result.transactions.append(txn)
        result.parsed_rows += 1

    return result


def normalize_statement_to_dict(
    content: str,
    file_format: str = "auto",
) -> dict[str, Any]:
    """
    Normalize a bank statement and return a JSON-serializable dict.
    """
    result = normalize_statement(content, file_format)
    return {
        "detected_format": result.detected_format,
        "total_rows": result.total_rows,
        "parsed_rows": result.parsed_rows,
        "skipped_rows": result.skipped_rows,
        "errors": result.errors,
        "transactions": [
            {
                "date": t.date.isoformat(),
                "description": t.description,
                "amount": float(t.amount),
                "transaction_type": t.transaction_type,
                "raw_amount": t.raw_amount,
                "raw_date": t.raw_date,
                "category_hint": t.category_hint,
                "reference": t.reference,
                "balance": float(t.balance) if t.balance is not None else None,
            }
            for t in result.transactions
        ],
    }
