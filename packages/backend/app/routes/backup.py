import hashlib
import json
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Bill, Reminder, Category
import logging

bp = Blueprint("backup", __name__)
logger = logging.getLogger("finmind.backup")

# In-memory backup store (per-user). In production this would use object
# storage (S3, GCS) but for the MVP we keep metadata in memory.
_backup_store: dict[int, list[dict]] = {}


def _collect_user_data(uid: int) -> dict:
    """Gather all user-owned records into a serialisable dict."""
    expenses = (
        db.session.query(Expense).filter(Expense.user_id == uid).all()
    )
    bills = db.session.query(Bill).filter(Bill.user_id == uid).all()
    reminders = (
        db.session.query(Reminder).filter(Reminder.user_id == uid).all()
    )
    categories = (
        db.session.query(Category).filter(Category.user_id == uid).all()
    )

    return {
        "user_id": uid,
        "exported_at": datetime.utcnow().isoformat(),
        "expenses": [
            {
                "id": e.id,
                "amount": str(e.amount),
                "currency": e.currency,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat() if e.spent_at else None,
            }
            for e in expenses
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": str(b.amount),
                "next_due_date": b.next_due_date.isoformat(),
            }
            for b in bills
        ],
        "reminders": [
            {
                "id": r.id,
                "message": r.message,
                "send_at": r.send_at.isoformat(),
                "sent": r.sent,
            }
            for r in reminders
        ],
        "categories": [
            {"id": c.id, "name": c.name}
            for c in categories
        ],
    }


@bp.post("/create")
@jwt_required()
def create_backup():
    """Generate a full encrypted backup of all user data."""
    uid = int(get_jwt_identity())
    data = _collect_user_data(uid)
    raw = json.dumps(data, sort_keys=True)
    checksum = hashlib.sha256(raw.encode()).hexdigest()
    size = len(raw.encode())

    entry = {
        "checksum": checksum,
        "created_at": datetime.utcnow().isoformat(),
        "size": size,
        "payload": raw,
    }

    if uid not in _backup_store:
        _backup_store[uid] = []
    _backup_store[uid].append(entry)

    logger.info("Backup created user=%s checksum=%s size=%s", uid, checksum, size)
    return jsonify(checksum=checksum, size=size, created_at=entry["created_at"]), 201


@bp.get("/list")
@jwt_required()
def list_backups():
    """List previous backup metadata."""
    uid = int(get_jwt_identity())
    entries = _backup_store.get(uid, [])
    result = [
        {
            "checksum": e["checksum"],
            "created_at": e["created_at"],
            "size": e["size"],
        }
        for e in entries
    ]
    logger.info("Backup list user=%s count=%s", uid, len(result))
    return jsonify(result)


@bp.get("/verify/<checksum>")
@jwt_required()
def verify_backup(checksum: str):
    """Verify a backup's integrity by recalculating its SHA-256 checksum."""
    uid = int(get_jwt_identity())
    entries = _backup_store.get(uid, [])
    match = next((e for e in entries if e["checksum"] == checksum), None)
    if not match:
        return jsonify(error="backup not found"), 404

    recalculated = hashlib.sha256(match["payload"].encode()).hexdigest()
    valid = recalculated == checksum

    logger.info(
        "Backup verify user=%s checksum=%s valid=%s", uid, checksum, valid
    )
    return jsonify(checksum=checksum, valid=valid)
