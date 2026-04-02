"""Account CRUD endpoints for multi-account financial tracking."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import exc

from ..extensions import db
from ..models import Account, AccountType

bp = Blueprint("accounts", __name__)


@bp.get("/")
@jwt_required()
def list_accounts():
    """List all accounts for the authenticated user."""
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    
    query = Account.query.filter(Account.user_id == uid)
    if not include_inactive:
        query = query.filter(Account.is_active.is_(True))
    
    accounts = query.order_by(Account.created_at.desc()).all()
    return jsonify({"accounts": [a.to_dict() for a in accounts]}), 200


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id):
    """Get a specific account by ID."""
    uid = int(get_jwt_identity())
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == uid
    ).first()
    
    if not account:
        return jsonify(error="Account not found"), 404
    
    return jsonify(account.to_dict()), 200


@bp.post("/")
@jwt_required()
def create_account():
    """Create a new financial account."""
    uid = int(get_jwt_identity())
    data = request.get_json()
    
    if not data:
        return jsonify(error="Request body required"), 400
    
    name = data.get("name", "").strip()
    if not name:
        return jsonify(error="Account name is required"), 400
    
    account_type_str = data.get("account_type", "CHECKING").upper()
    try:
        account_type = AccountType(account_type_str)
    except ValueError:
        return jsonify(error=f"Invalid account type. Valid types: {[t.value for t in AccountType]}"), 400
    
    balance = data.get("balance", 0)
    try:
        balance = float(balance)
    except (TypeError, ValueError):
        return jsonify(error="Balance must be a valid number"), 400
    
    currency = data.get("currency", "INR").strip().upper()[:10]
    
    account = Account(
        user_id=uid,
        name=name,
        account_type=account_type,
        balance=balance,
        currency=currency,
        is_active=data.get("is_active", True),
    )
    
    try:
        db.session.add(account)
        db.session.commit()
        return jsonify(account.to_dict()), 201
    except exc.IntegrityError:
        db.session.rollback()
        return jsonify(error="Failed to create account"), 400


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    """Update an existing account."""
    uid = int(get_jwt_identity())
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == uid
    ).first()
    
    if not account:
        return jsonify(error="Account not found"), 404
    
    data = request.get_json()
    if not data:
        return jsonify(error="Request body required"), 400
    
    if "name" in data:
        name = data["name"].strip()
        if not name:
            return jsonify(error="Account name cannot be empty"), 400
        account.name = name
    
    if "account_type" in data:
        try:
            account.account_type = AccountType(data["account_type"].upper())
        except ValueError:
            return jsonify(error=f"Invalid account type. Valid types: {[t.value for t in AccountType]}"), 400
    
    if "balance" in data:
        try:
            account.balance = float(data["balance"])
        except (TypeError, ValueError):
            return jsonify(error="Balance must be a valid number"), 400
    
    if "currency" in data:
        account.currency = data["currency"].strip().upper()[:10]
    
    if "is_active" in data:
        account.is_active = bool(data["is_active"])
    
    try:
        db.session.commit()
        return jsonify(account.to_dict()), 200
    except exc.IntegrityError:
        db.session.rollback()
        return jsonify(error="Failed to update account"), 400


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    """Delete an account (soft delete by setting is_active=False)."""
    uid = int(get_jwt_identity())
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == uid
    ).first()
    
    if not account:
        return jsonify(error="Account not found"), 404
    
    # Soft delete
    account.is_active = False
    db.session.commit()
    
    return jsonify(message="Account deactivated successfully"), 200


@bp.delete("/<int:account_id>/hard")
@jwt_required()
def hard_delete_account(account_id):
    """Permanently delete an account."""
    uid = int(get_jwt_identity())
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == uid
    ).first()
    
    if not account:
        return jsonify(error="Account not found"), 404
    
    db.session.delete(account)
    db.session.commit()
    
    return jsonify(message="Account deleted permanently"), 200