"""Bank sync API endpoints."""

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import bank_sync

bp = Blueprint("bank_sync", __name__)
logger = logging.getLogger("finmind.bank_sync")


@bp.get("/providers")
@jwt_required()
def list_providers():
    """Return available bank connector providers."""
    return jsonify(providers=bank_sync.get_available_providers())


@bp.post("/connect")
@jwt_required()
def connect():
    """Initiate a bank connection."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    provider = (data.get("provider") or "").strip()
    if not provider:
        return jsonify(error="provider required"), 400

    try:
        result = bank_sync.initiate_connection(
            user_id=uid,
            provider=provider,
            mobile=data.get("mobile"),
            redirect_url=data.get("redirect_url"),
            currency=data.get("currency", "INR"),
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503

    logger.info("Bank connect initiated user=%s provider=%s", uid, provider)
    return jsonify(result), 201


@bp.post("/connections/<int:conn_id>/confirm")
@jwt_required()
def confirm(conn_id: int):
    """Check consent status and discover accounts."""
    uid = int(get_jwt_identity())
    try:
        result = bank_sync.confirm_consent(conn_id, uid)
    except LookupError:
        return jsonify(error="not found"), 404
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(result)


@bp.post("/connections/<int:conn_id>/select-account")
@jwt_required()
def select_account(conn_id: int):
    """Select which bank account to sync."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    account_id = (data.get("account_id") or "").strip()
    if not account_id:
        return jsonify(error="account_id required"), 400

    try:
        result = bank_sync.select_account(conn_id, uid, account_id)
    except LookupError:
        return jsonify(error="not found"), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@bp.get("/connections")
@jwt_required()
def list_connections():
    """List all bank connections for the user."""
    uid = int(get_jwt_identity())
    return jsonify(bank_sync.get_connections(uid))


@bp.post("/connections/<int:conn_id>/sync")
@jwt_required()
def sync(conn_id: int):
    """Trigger a full sync for a connection."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    from_date = _parse_date(data.get("from_date"))
    to_date = _parse_date(data.get("to_date"))

    try:
        result = bank_sync.sync_connection(
            conn_id, uid, from_date=from_date, to_date=to_date
        )
    except LookupError:
        return jsonify(error="not found"), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    return jsonify(result)


@bp.post("/connections/<int:conn_id>/refresh")
@jwt_required()
def refresh(conn_id: int):
    """Trigger an incremental refresh using stored cursor."""
    uid = int(get_jwt_identity())
    try:
        result = bank_sync.refresh_connection(conn_id, uid)
    except LookupError:
        return jsonify(error="not found"), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@bp.get("/connections/<int:conn_id>/logs")
@jwt_required()
def sync_logs(conn_id: int):
    """Get sync history for a connection."""
    uid = int(get_jwt_identity())
    try:
        logs = bank_sync.get_sync_logs(conn_id, uid)
    except LookupError:
        return jsonify(error="not found"), 404
    return jsonify(logs)


@bp.delete("/connections/<int:conn_id>")
@jwt_required()
def disconnect(conn_id: int):
    """Remove a bank connection."""
    uid = int(get_jwt_identity())
    try:
        bank_sync.disconnect(conn_id, uid)
    except LookupError:
        return jsonify(error="not found"), 404
    return jsonify(message="disconnected")


def _parse_date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None
