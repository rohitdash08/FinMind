"""Data Export Service for FinMind.

Export financial data in multiple formats:
- CSV (spreadsheet compatible)
- JSON (structured data)
- OFX (financial software compatible)
- PDF summary report

Supports filtering by date range, category, merchant.
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

from ..extensions import db

logger = logging.getLogger("finmind.export")


def _filter_transactions(transactions: list[dict], filters: dict = None) -> list[dict]:
    """Apply filters to transactions."""
    if not filters:
        return transactions

    filtered = transactions
    if filters.get("start_date"):
        start = filters["start_date"]
        filtered = [t for t in filtered if t.get("date", "") >= start]
    if filters.get("end_date"):
        end = filters["end_date"]
        filtered = [t for t in filtered if t.get("date", "") <= end]
    if filters.get("category"):
        categories = set(filters["category"]) if isinstance(filters["category"], list) else {filters["category"]}
        filtered = [t for t in filtered if t.get("category") in categories]
    if filters.get("merchant"):
        merchants = set(filters["merchant"]) if isinstance(filters["merchant"], list) else {filters["merchant"]}
        filtered = [t for t in filtered if t.get("merchant") in merchants]
    if filters.get("min_amount"):
        filtered = [t for t in filtered if float(t.get("amount", 0)) >= filters["min_amount"]]
    if filters.get("max_amount"):
        filtered = [t for t in filtered if float(t.get("amount", 0)) <= filters["max_amount"]]

    return filtered


def export_csv(transactions: list[dict], filters: dict = None) -> str:
    """Export transactions as CSV string."""
    filtered = _filter_transactions(transactions, filters)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["Date", "Merchant", "Category", "Amount", "Currency", "Description", "Tags"])

    for tx in filtered:
        writer.writerow([
            tx.get("date", ""),
            tx.get("merchant", ""),
            tx.get("category", ""),
            tx.get("amount", 0),
            tx.get("currency", "USD"),
            tx.get("description", ""),
            ",".join(tx.get("tags", [])) if isinstance(tx.get("tags"), list) else tx.get("tags", ""),
        ])

    return output.getvalue()


def export_json(transactions: list[dict], filters: dict = None) -> dict:
    """Export transactions as structured JSON."""
    filtered = _filter_transactions(transactions, filters)

    total = sum(float(t.get("amount", 0)) for t in filtered)
    categories = defaultdict(float)
    merchants = defaultdict(float)

    for tx in filtered:
        categories[tx.get("category", "uncategorized")] += float(tx.get("amount", 0))
        merchants[tx.get("merchant", "Unknown")] += float(tx.get("amount", 0))

    return {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "total_transactions": len(filtered),
        "total_amount": round(total, 2),
        "categories_summary": {k: round(v, 2) for k, v in sorted(categories.items(), key=lambda x: x[1], reverse=True)},
        "merchants_summary": {k: round(v, 2) for k, v in sorted(merchants.items(), key=lambda x: x[1], reverse=True)},
        "transactions": filtered,
    }


def export_ofx(transactions: list[dict], filters: dict = None,
               account_id: str = "finmind-export", bank_id: str = "FinMind") -> str:
    """Export transactions in OFX format (for financial software import)."""
    filtered = _filter_transactions(transactions, filters)

    lines = [
        "OFXHEADER:100",
        "DATA:OFXSGML",
        "VERSION:102",
        "SECURITY:NONE",
        "ENCODING:USASCII",
        "CHARSET:1252",
        "COMPRESSION:NONE",
        "OLDFILEUID:NONE",
        "NEWFILEUID:NONE",
        "",
        "<OFX>",
        "<BANKMSGSRSV1>",
        "<STMTTRNRS>",
        "<TRNUID>1001",
        "<STATUS>",
        "<CODE>0",
        "<SEVERITY>INFO",
        "</STATUS>",
        "<STMTRS>",
        "<CURDEF>USD",
        f"<BANKACCTFROM><BANKID>{bank_id}<ACCTID>{account_id}<ACCTTYPE>CHECKING</BANKACCTFROM>",
        "<BANKTRANLIST>",
    ]

    for tx in filtered:
        date_str = tx.get("date", "")
        # OFX date format: YYYYMMDD
        ofx_date = date_str[:10].replace("-", "") if date_str else "20250101"
        amount = float(tx.get("amount", 0))
        trn_type = "CREDIT" if amount > 0 else "DEBIT"

        lines.extend([
            "<STMTTRN>",
            f"<TRNTYPE>{trn_type}",
            f"<DTPOSTED>{ofx_date}",
            f"<TRNAMT>{amount:.2f}",
            f"<FITID>{tx.get('id', hash(str(tx)))}",
            f"<NAME>{tx.get('merchant', 'Unknown')}",
            f"<MEMO>{tx.get('category', '')}: {tx.get('description', '')}",
            "</STMTTRN>",
        ])

    lines.extend([
        "</BANKTRANLIST>",
        f"<LEDGERBAL><BALAMT>{sum(float(t.get('amount', 0)) for t in filtered):.2f}<DTASOF>{datetime.now(timezone.utc).strftime('%Y%m%d')}</LEDGERBAL>",
        "</STMTRS>",
        "</STMTTRNRS>",
        "</BANKMSGSRSV1>",
        "</OFX>",
    ])

    return "\n".join(lines)


def generate_summary_report(transactions: list[dict], filters: dict = None) -> dict:
    """Generate a summary report for PDF export."""
    filtered = _filter_transactions(transactions, filters)

    total = sum(float(t.get("amount", 0)) for t in filtered)
    categories = defaultdict(float)

    for tx in filtered:
        categories[tx.get("category", "uncategorized")] += float(tx.get("amount", 0))

    avg_daily = total / 30 if total else 0

    return {
        "report_date": datetime.now(timezone.utc).isoformat(),
        "period": {
            "start": filters.get("start_date") if filters else None,
            "end": filters.get("end_date") if filters else None,
        },
        "total_transactions": len(filtered),
        "total_spending": round(total, 2),
        "average_daily_spending": round(avg_daily, 2),
        "category_breakdown": {k: round(v, 2) for k, v in sorted(categories.items(), key=lambda x: x[1], reverse=True)},
        "top_category": max(categories.items(), key=lambda x: x[1])[0] if categories else None,
        "top_category_amount": round(max(categories.values()), 2) if categories else 0,
    }
