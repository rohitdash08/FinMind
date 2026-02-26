"""Multi-account API routes."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from decimal import Decimal

from ..extensions import db
from ..models_accounts import FinancialAccount, AccountType
from ..models import Expense, Bill

bp = Blueprint("accounts", __name__)


@bp.post("")
@jwt_required()
def create_account():
    """Create a new financial account."""
    uid = int(get_jwt_identity())
    data = request.get_json()
    
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Account name is required"}), 400
    
    account_type = data.get("account_type", "CHECKING")
    if account_type not in [e.value for e in AccountType]:
        return jsonify({"error": f"Invalid account type"}), 400
    
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        balance=Decimal(str(data.get("balance", 0))),
        currency=data.get("currency", "INR"),
        institution=data.get("institution"),
        account_number_last4=data.get("account_number_last4"),
        color=data.get("color"),
        icon=data.get("icon")
    )
    
    db.session.add(account)
    db.session.commit()
    
    return jsonify({"account": account.to_dict()}), 201


@bp.get("")
@jwt_required()
def list_accounts():
    """List all active financial accounts."""
    uid = int(get_jwt_identity())
    accounts = FinancialAccount.query.filter_by(
        user_id=uid,
        is_active=True
    ).order_by(FinancialAccount.created_at.desc()).all()
    
    return jsonify({"accounts": [a.to_dict() for a in accounts]}), 200


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id):
    """Get a single account."""
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(
        id=account_id,
        user_id=uid
    ).first()
    
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    return jsonify({"account": account.to_dict()}), 200


@bp.put("/<int:account_id>")
@jwt_required()
def update_account(account_id):
    """Update an account."""
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(
        id=account_id,
        user_id=uid
    ).first()
    
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    data = request.get_json()
    
    if "name" in data:
        account.name = data["name"].strip()
    if "account_type" in data:
        if data["account_type"] not in [e.value for e in AccountType]:
            return jsonify({"error": "Invalid account type"}), 400
        account.account_type = data["account_type"]
    if "balance" in data:
        account.balance = Decimal(str(data["balance"]))
    if "currency" in data:
        account.currency = data["currency"]
    if "institution" in data:
        account.institution = data["institution"]
    if "account_number_last4" in data:
        account.account_number_last4 = data["account_number_last4"]
    if "color" in data:
        account.color = data["color"]
    if "icon" in data:
        account.icon = data["icon"]
    
    db.session.commit()
    
    return jsonify({"account": account.to_dict()}), 200


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id):
    """Soft delete (deactivate) an account."""
    uid = int(get_jwt_identity())
    account = FinancialAccount.query.filter_by(
        id=account_id,
        user_id=uid
    ).first()
    
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    account.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Account deactivated"}), 200


@bp.get("/overview")
@jwt_required()
def get_overview():
    """Get multi-account overview with aggregated data."""
    uid = int(get_jwt_identity())
    
    # Get all active accounts
    accounts = FinancialAccount.query.filter_by(
        user_id=uid,
        is_active=True
    ).all()
    
    # Calculate totals by currency
    totals_by_currency = {}
    totals_by_type = {}
    
    for account in accounts:
        currency = account.currency
        account_type = account.account_type
        balance = float(account.balance)
        
        if currency not in totals_by_currency:
            totals_by_currency[currency] = 0
        totals_by_currency[currency] += balance
        
        if account_type not in totals_by_type:
            totals_by_type[account_type] = 0
        totals_by_type[account_type] += balance
    
    # Get recent expenses across all accounts
    recent_expenses = Expense.query.filter_by(
        user_id=uid
    ).order_by(Expense.spent_at.desc()).limit(10).all()
    
    # Get upcoming bills
    from datetime import date
    upcoming_bills = Bill.query.filter(
        Bill.user_id == uid,
        Bill.active.is_(True),
        Bill.next_due_date >= date.today()
    ).order_by(Bill.next_due_date.asc()).limit(5).all()
    
    return jsonify({
        "accounts": [a.to_dict() for a in accounts],
        "summary": {
            "total_accounts": len(accounts),
            "totals_by_currency": totals_by_currency,
            "totals_by_type": totals_by_type
        },
        "recent_expenses": [{
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat(),
            "expense_type": e.expense_type
        } for e in recent_expenses],
        "upcoming_bills": [{
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat()
        } for b in upcoming_bills]
    }), 200
