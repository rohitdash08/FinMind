"""Bulk import validation & preview (issue #115)."""
import csv, io, logging
from datetime import date
from decimal import Decimal, InvalidOperation

logger = logging.getLogger("finmind.import")

REQUIRED_COLS = {"amount", "spent_at"}
OPTIONAL_COLS = {"notes", "currency", "category", "expense_type"}
ALL_COLS = REQUIRED_COLS | OPTIONAL_COLS


def parse_csv(raw: str) -> dict:
    reader = csv.DictReader(io.StringIO(raw.strip()))
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    missing = REQUIRED_COLS - headers
    unknown = headers - ALL_COLS

    errors, warnings, preview = [], [], []

    if missing:
        errors.append(f"Missing required columns: {', '.join(sorted(missing))}")
        return {"valid": False, "errors": errors, "warnings": [], "preview": [], "row_count": 0}

    if unknown:
        warnings.append(f"Unknown columns will be ignored: {', '.join(sorted(unknown))}")

    for i, row in enumerate(reader, start=2):
        row_errors = []
        # Validate amount
        try:
            amt = Decimal(str(row.get("amount","")).strip())
            if amt <= 0: row_errors.append(f"Row {i}: amount must be > 0")
        except InvalidOperation:
            row_errors.append(f"Row {i}: invalid amount '{row.get('amount')}'")
            amt = None

        # Validate date
        raw_date = str(row.get("spent_at","")).strip()
        parsed_date = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
            try: parsed_date = date.fromisoformat(raw_date) if fmt == "%Y-%m-%d" else date.strptime(raw_date, fmt); break
            except ValueError: continue
        if not parsed_date:
            row_errors.append(f"Row {i}: invalid date '{raw_date}' (use YYYY-MM-DD)")

        errors.extend(row_errors)
        if not row_errors:
            preview.append({
                "row": i, "amount": float(amt) if amt else None,
                "spent_at": parsed_date.isoformat() if parsed_date else None,
                "notes": row.get("notes","").strip(),
                "currency": (row.get("currency","INR") or "INR").strip().upper(),
                "expense_type": (row.get("expense_type","EXPENSE") or "EXPENSE").strip().upper(),
            })

    return {
        "valid": len(errors) == 0,
        "errors": errors, "warnings": warnings,
        "preview": preview[:10],  # first 10 for preview
        "row_count": len(preview),
        "total_rows_parsed": i - 1 if preview or errors else 0,
    }
