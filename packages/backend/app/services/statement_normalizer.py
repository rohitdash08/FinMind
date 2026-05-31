import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from ..extensions import db
from ..models import Expense
import logging

logger = logging.getLogger("finmind.statement_normalizer")

_adapters: dict[str, dict] = {}


def _init_default_adapters():
    if _adapters:
        return
    _adapters["csv_generic"] = {
        "name": "CSV Generic",
        "format": "CSV",
        "schema_map": {
            "date": {"field": "date", "fallback": ["spent_at", "transaction_date"]},
            "amount": {"field": "amount", "fallback": ["value", "sum"]},
            "description": {"field": "description", "fallback": ["notes", "memo", "payee"]},
        },
    }
    _adapters["ofx_standard"] = {
        "name": "OFX Standard",
        "format": "OFX",
        "schema_map": {
            "date": {"field": "DTPOSTED", "fallback": []},
            "amount": {"field": "TRNAMT", "fallback": []},
            "description": {"field": "NAME", "fallback": ["MEMO"]},
        },
    }
    _adapters["qif_standard"] = {
        "name": "QIF Standard",
        "format": "QIF",
        "schema_map": {
            "date": {"field": "D", "fallback": []},
            "amount": {"field": "T", "fallback": []},
            "description": {"field": "P", "fallback": ["M"]},
        },
    }


def get_adapters() -> list[dict]:
    _init_default_adapters()
    return [
        {
            "name": v["name"],
            "format": v["format"],
            "fields": list(v["schema_map"].keys()),
        }
        for v in _adapters.values()
    ]


def register_adapter(data: dict) -> dict:
    key = data["name"].lower().replace(" ", "_")
    _adapters[key] = {
        "name": data["name"],
        "format": data["format"],
        "schema_map": data["schema_map"],
    }
    logger.info("Registered adapter key=%s format=%s", key, data["format"])
    return {"key": key, "name": data["name"], "format": data["format"]}


def _detect_format(filename: str, content: bytes) -> str | None:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return "CSV"
    if name.endswith(".ofx") or name.endswith(".qfx"):
        return "OFX"
    if name.endswith(".qif"):
        return "QIF"
    if name.endswith(".pdf"):
        return "PDF"
    try:
        text = content.decode("utf-8", errors="ignore")
        if text.strip().startswith("OFXHEADER") or "<OFX>" in text:
            return "OFX"
        if text.strip().startswith("!Type:"):
            return "QIF"
        if "," in text[:500]:
            return "CSV"
    except Exception:
        pass
    return None


def _pick_adapter(detected_format: str, adapter_name: str | None) -> dict | None:
    _init_default_adapters()
    if adapter_name:
        key = adapter_name.lower().replace(" ", "_")
        if key in _adapters:
            return _adapters[key]
    for key, adapter in _adapters.items():
        if adapter["format"] == detected_format:
            return adapter
    return None


def _parse_csv_with_adapter(content: bytes, adapter: dict) -> list[dict]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    smap = adapter["schema_map"]
    rows = []
    for row in reader:
        normalized = {}
        for target, mapping in smap.items():
            val = row.get(mapping["field"])
            if not val and mapping.get("fallback"):
                for fb in mapping["fallback"]:
                    val = row.get(fb)
                    if val:
                        break
            normalized[target] = (val or "").strip()
        rows.append(normalized)
    return rows


def _parse_ofx(content: bytes) -> list[dict]:
    text = content.decode("utf-8", errors="ignore")
    transactions = []
    current = {}
    for line in text.splitlines():
        line = line.strip()
        if line == "<STMTTRN>":
            current = {}
        elif line == "</STMTTRN>":
            if current.get("DTPOSTED") and current.get("TRNAMT"):
                date_str = current["DTPOSTED"]
                if len(date_str) >= 8:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                transactions.append({
                    "date": date_str,
                    "amount": current.get("TRNAMT", ""),
                    "description": current.get("NAME", current.get("MEMO", "")),
                })
            current = {}
        elif ">" in line:
            key, _, val = line.partition(">")
            current[key.strip("<")] = val.strip()
    return transactions


def _parse_qif(content: bytes) -> list[dict]:
    text = content.decode("utf-8", errors="ignore")
    transactions = []
    current = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == "^":
            if current:
                transactions.append(current)
                current = {}
        elif line.startswith("D"):
            current["date"] = line[1:].strip()
        elif line.startswith("T"):
            current["amount"] = line[1:].strip()
        elif line.startswith("P"):
            current["description"] = line[1:].strip()
        elif line.startswith("M"):
            current["memo"] = line[1:].strip()
    if current:
        transactions.append(current)
    for t in transactions:
        t.setdefault("description", t.pop("memo", ""))
    return transactions


def _normalize_row(row: dict) -> dict | None:
    dt = _normalize_date(row.get("date"))
    amt = _normalize_amount(row.get("amount"))
    desc = str(row.get("description") or row.get("memo") or "").strip()
    if not dt or amt is None or not desc:
        return None
    return {
        "date": dt,
        "amount": float(abs(amt)),
        "description": desc[:500],
        "currency": "USD",
    }


def _normalize_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y%m%d"):
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
    raw = str(value).strip().replace("$", "").replace(",", "")
    negative_parens = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"[^\d\.\-]", "", raw)
    if not cleaned:
        return None
    try:
        out = Decimal(cleaned).quantize(Decimal("0.01"))
        return -abs(out) if negative_parens else out
    except (InvalidOperation, ValueError):
        return None


def _is_duplicate(uid: int, row: dict) -> bool:
    amt = _normalize_amount(row.get("amount"))
    if amt is None:
        return False
    try:
        spent_at = date.fromisoformat(row["date"])
    except (ValueError, KeyError):
        return False
    return (
        db.session.query(Expense)
        .filter_by(
            user_id=uid,
            spent_at=spent_at,
            amount=amt,
            notes=row.get("description", ""),
        )
        .first()
        is not None
    )


def preview_normalization(user_id: int, filename: str, content: bytes, adapter_name: str | None = None) -> dict:
    detected = _detect_format(filename, content)
    if not detected:
        raise ValueError("Unable to detect file format. Supported: CSV, OFX, QIF, PDF")

    adapter = _pick_adapter(detected, adapter_name)
    if not adapter:
        raise ValueError(f"No adapter available for format: {detected}")

    if detected == "CSV":
        rows = _parse_csv_with_adapter(content, adapter)
    elif detected == "OFX":
        rows = _parse_ofx(content)
    elif detected == "QIF":
        rows = _parse_qif(content)
    else:
        raise ValueError(f"PDF parsing is handled by the existing import pipeline")

    normalized = []
    for row in rows:
        nr = _normalize_row(row)
        if nr:
            normalized.append(nr)

    duplicates = sum(1 for r in normalized if _is_duplicate(user_id, r))
    return {
        "total": len(normalized),
        "duplicates": duplicates,
        "transactions": normalized,
        "detected_format": detected,
        "adapter": adapter["name"],
    }


def commit_normalization(user_id: int, rows: list[dict]) -> dict:
    inserted = 0
    duplicates = 0
    for row in rows:
        if _is_duplicate(user_id, row):
            duplicates += 1
            continue
        amt = _normalize_amount(row.get("amount"))
        if amt is None:
            continue
        try:
            spent_at = date.fromisoformat(row["date"])
        except (ValueError, KeyError):
            continue
        expense = Expense(
            user_id=user_id,
            amount=abs(amt),
            notes=(row.get("description") or "")[:500],
            spent_at=spent_at,
            expense_type="EXPENSE" if amt < 0 else "INCOME",
        )
        db.session.add(expense)
        inserted += 1
    db.session.commit()
    logger.info("Normalized import user=%s inserted=%s duplicates=%s", user_id, inserted, duplicates)
    return {"inserted": inserted, "duplicates": duplicates}
