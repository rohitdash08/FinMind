"""Bank Account Sync API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.bank_sync import BankSyncService

bp = Blueprint("bank_sync", __name__)

# Per-user service instances
_services = {}


def _get_service(user_id: str) -> BankSyncService:
    if user_id not in _services:
        _services[user_id] = BankSyncService()
    return _services[user_id]


@bp.post("/accounts")
@jwt_required()
def register_account():
    """Register a bank account."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    result = service.register_account(
        account_id=data.get("account_id"),
        account_type=data.get("account_type", "checking"),
        institution=data.get("institution", ""),
        balance=float(data.get("balance", 0)),
    )
    return jsonify(result)


@bp.post("/sync/<account_id>")
@jwt_required()
def sync_account(account_id: str):
    """Sync a specific account."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    result = service.sync_account(
        account_id=account_id,
        bank_transactions=data.get("transactions", []),
        reported_balance=float(data.get("balance")) if "balance" in data else None,
    )
    return jsonify(result)


@bp.post("/sync-all")
@jwt_required()
def sync_all():
    """Sync all registered accounts."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    result = service.sync_all(bank_data=data.get("accounts", {}))
    return jsonify(result)


@bp.get("/accounts")
@jwt_required()
def list_accounts():
    """List all registered accounts."""
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"accounts": service.get_accounts()})


@bp.get("/history")
@jwt_required()
def sync_history():
    """Get sync history."""
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"history": service.get_sync_history()})
