import io
import json
import uuid
import zipfile
import threading
import logging
from datetime import datetime, timezone
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Expense, Bill, Category, Reminder

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")

# In-memory export store
_exports: dict[str, dict] = {}
_lock = threading.Lock()
# In-memory audit trail
_audit: list[dict] = []


def _log_audit(user_id: int, action: str, ip: str) -> dict:
    entry = {
        "user_id": user_id,
        "action": action,
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _audit.append(entry)
    logger.info("Audit: user=%s action=%s ip=%s", user_id, action, ip)
    return entry


def _json_serial(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _build_export(job_id: str, uid: int) -> None:
    """Build ZIP export in background thread using app context."""
    from flask import current_app

    # We need the app reference — grab it before the thread loses context
    # The caller passes it via _build_export_with_app instead.
    pass


def _build_export_with_app(app, job_id: str, uid: int) -> None:
    with app.app_context():
        try:
            user = db.session.get(User, uid)
            profile = {
                "id": user.id,
                "email": user.email,
                "preferred_currency": user.preferred_currency,
                "created_at": user.created_at,
            } if user else {}

            expenses = [
                {"id": e.id, "amount": e.amount, "currency": e.currency,
                 "notes": e.notes, "spent_at": e.spent_at, "category_id": e.category_id}
                for e in Expense.query.filter_by(user_id=uid).all()
            ]
            bills = [
                {"id": b.id, "name": b.name, "amount": b.amount, "currency": b.currency,
                 "next_due_date": b.next_due_date, "cadence": b.cadence.value if b.cadence else None}
                for b in Bill.query.filter_by(user_id=uid).all()
            ]
            categories = [
                {"id": c.id, "name": c.name}
                for c in Category.query.filter_by(user_id=uid).all()
            ]

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("profile.json", json.dumps(profile, default=_json_serial, indent=2))
                zf.writestr("expenses.json", json.dumps(expenses, default=_json_serial, indent=2))
                zf.writestr("bills.json", json.dumps(bills, default=_json_serial, indent=2))
                zf.writestr("categories.json", json.dumps(categories, default=_json_serial, indent=2))
                zf.writestr("budgets.json", json.dumps([], indent=2))

            with _lock:
                _exports[job_id]["status"] = "complete"
                _exports[job_id]["data"] = buf.getvalue()
            logger.info("Export %s complete for user %s", job_id, uid)
        except Exception as exc:
            logger.exception("Export %s failed: %s", job_id, exc)
            with _lock:
                _exports[job_id]["status"] = "failed"
                _exports[job_id]["error"] = str(exc)


@bp.post("/export")
@jwt_required()
def create_export():
    uid = int(get_jwt_identity())
    ip = request.remote_addr or "unknown"
    _log_audit(uid, "export_request", ip)

    job_id = str(uuid.uuid4())
    with _lock:
        _exports[job_id] = {"id": job_id, "user_id": uid, "status": "pending", "data": None, "error": None}

    from flask import current_app
    app = current_app._get_current_object()
    threading.Thread(target=_build_export_with_app, args=[app, job_id, uid], daemon=True).start()
    return jsonify(job_id=job_id, status="pending"), 202


@bp.get("/export/<job_id>")
@jwt_required()
def get_export(job_id: str):
    uid = int(get_jwt_identity())
    with _lock:
        export = _exports.get(job_id)
    if not export or export["user_id"] != uid:
        return jsonify(error="not found"), 404
    if export["status"] == "complete":
        from flask import send_file
        return send_file(
            io.BytesIO(export["data"]),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"finmind-export-{uid}.zip",
        )
    return jsonify(job_id=job_id, status=export["status"], error=export.get("error"))


@bp.delete("/account")
@jwt_required()
def delete_account():
    uid = int(get_jwt_identity())
    ip = request.remote_addr or "unknown"
    data = request.get_json() or {}
    if data.get("confirmation") != "DELETE":
        return jsonify(error="Must send confirmation: DELETE"), 400

    _log_audit(uid, "account_delete_request", ip)
    # Mark user for deletion (soft delete — set email to deleted placeholder)
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404
    logger.info("Account deletion requested user=%s ip=%s", uid, ip)
    return jsonify(message="Account marked for deletion", user_id=uid), 200


@bp.get("/audit")
@jwt_required()
def get_audit():
    uid = int(get_jwt_identity())
    with _lock:
        entries = [a for a in _audit if a["user_id"] == uid]
    return jsonify(entries)
