from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from ..extensions import db
from ..models import FinancialAccount

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("/accounts", methods=["GET"])
@login_required
def get_accounts():
    """Get all financial accounts for current user."""
    accounts = FinancialAccount.query.filter_by(user_id=current_user.id, is_active=True).all()
    return jsonify([{
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "balance": float(a.balance),
        "currency": a.currency,
        "color": a.color,
        "icon": a.icon,
        "created_at": a.created_at.isoformat() if a.created_at else None
    } for a in accounts])


@accounts_bp.route("/accounts", methods=["POST"])
@login_required
def create_account():
    """Create a new financial account."""
    data = request.get_json()
    name = data.get("name")
    account_type = data.get("account_type", "bank")
    balance = data.get("balance", 0)
    currency = data.get("currency", "USD")
    color = data.get("color", "#3B82F6")
    icon = data.get("icon", "wallet")
    
    if not name:
        return jsonify({"error": "Account name is required"}), 400
    
    account = FinancialAccount(
        user_id=current_user.id,
        name=name,
        account_type=account_type,
        balance=balance,
        currency=currency,
        color=color,
        icon=icon
    )
    db.session.add(account)
    db.session.commit()
    
    return jsonify({
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "balance": float(account.balance),
        "currency": account.currency,
        "color": account.color,
        "icon": account.icon
    }), 201


@accounts_bp.route("/accounts/<int:account_id>", methods=["GET"])
@login_required
def get_account(account_id):
    """Get a specific account."""
    account = FinancialAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    return jsonify({
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "balance": float(account.balance),
        "currency": account.currency,
        "color": account.color,
        "icon": account.icon,
        "is_active": account.is_active
    })


@accounts_bp.route("/accounts/<int:account_id>", methods=["PUT"])
@login_required
def update_account(account_id):
    """Update an account."""
    account = FinancialAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    data = request.get_json()
    if "name" in data:
        account.name = data["name"]
    if "account_type" in data:
        account.account_type = data["account_type"]
    if "balance" in data:
        account.balance = data["balance"]
    if "currency" in data:
        account.currency = data["currency"]
    if "color" in data:
        account.color = data["color"]
    if "icon" in data:
        account.icon = data["icon"]
    
    db.session.commit()
    
    return jsonify({
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "balance": float(account.balance),
        "currency": account.currency
    })


@accounts_bp.route("/accounts/<int:account_id>", methods=["DELETE"])
@login_required
def delete_account(account_id):
    """Soft delete an account."""
    account = FinancialAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    account.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Account deleted"})


@accounts_bp.route("/accounts/summary", methods=["GET"])
@login_required
def get_accounts_summary():
    """Get total balance across all accounts."""
    accounts = FinancialAccount.query.filter_by(user_id=current_user.id, is_active=True).all()
    
    total_by_currency = {}
    for a in accounts:
        if a.currency not in total_by_currency:
            total_by_currency[a.currency] = 0
        total_by_currency[a.currency] += float(a.balance)
    
    return jsonify({
        "accounts": [{
            "id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "balance": float(a.balance),
            "currency": a.currency,
            "color": a.color
        } for a in accounts],
        "total": total_by_currency,
        "total_currencies": len(total_by_currency)
    })
