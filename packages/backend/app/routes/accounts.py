"""Multi-account API routes for financial account management."""
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models_accounts import FinancialAccount, AccountType
from ..models import Expense, Bill
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import func

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("", methods=["POST"])
def create_account():
    """Create a new financial account."""
    data = request.get_json()
    name = data.get("name", "").strip()
    account_type = data.get("account_type", "CHECKING")
    balance = data.get("balance", 0)
    currency = data.get("currency", "INR")
    institution = data.get("institution")
    account_number_last4 = data.get("account_number_last4")
    color = data.get("color")
    icon = data.get("icon")
    
    if not name:
        return jsonify({"error": "Account name is required"}), 400
    
    if account_type not in [e.value for e in AccountType]:
        return jsonify({"error": f"Invalid account type. Valid types: {[e.value for e in AccountType]}"}), 400
    
    account = FinancialAccount(
        user_id=g.user.id,
        name=name,
        account_type=account_type,
        balance=Decimal(str(balance)),
        currency=currency,
        institution=institution,
        account_number_last4=account_number_last4,
        color=color,
        icon=icon
    )
    
    db.session.add(account)
    db.session.commit()
    
    return jsonify({
        "message": "Account created successfully",
        "account": {
            "id": account.id,
            "name": account.name,
            "account_type": account.account_type,
            "balance": float(account.balance),
            "currency": account.currency,
            "institution": account.institution,
            "is_active": account.is_active,
            "created_at": account.created_at.isoformat()
        }
    }), 201


@bp.route("", methods=["GET"])
def list_accounts():
    """List all financial accounts for the current user."""
    accounts = FinancialAccount.query.filter_by(
        user_id=g.user.id,
        is_active=True
    ).order_by(FinancialAccount.created_at.desc()).all()
    
    return jsonify({
        "accounts": [{
            "id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "balance": float(a.balance),
            "formatted_balance": a.formatted_balance,
            "currency": a.currency,
            "institution": a.institution,
            "account_number_last4": a.account_number_last4,
            "color": a.color,
            "icon": a.icon,
            "is_active": a.is_active,
            "created_at": a.created_at.isoformat()
        } for a in accounts]
    }), 200


@bp.route("/<int:account_id>", methods=["GET"])
def get_account(account_id):
    """Get a specific account."""
    account = FinancialAccount.query.filter_by(
        id=account_id,
        user_id=g.user.id
    ).first()
    
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    return jsonify({
        "account": {
            "id": account.id,
            "name": account.name,
            "account_type": account.account_type,
            "balance": float(account.balance),
            "formatted_balance": account.formatted_balance,
            "currency": account.currency,
            "institution": account.institution,
            "account_number_last4": account.account_number_last4,
            "color": account.color,
            "icon": account.icon,
            "is_active": account.is_active,
            "created_at": account.created_at.isoformat(),
            "updated_at": account.updated_at.isoformat()
        }
    }), 200


@bp.route("/<int:account_id>", methods=["PUT"])
def update_account(account_id):
    """Update an account."""
    account = FinancialAccount.query.filter_by(
        id=account_id,
        user_id=g.user.id
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
    if "institution" in data:
        account.institution = data["institution"]
    if "account_number_last4" in data:
        account.account_number_last4 = data["account_number_last4"]
    if "color" in data:
        account.color = data["color"]
    if "icon" in data:
        account.icon = data["icon"]
    if "is_active" in data:
        account.is_active = data["is_active"]
    
    db.session.commit()
    
    return jsonify({
        "message": "Account updated successfully",
        "account": {
            "id": account.id,
            "name": account.name,
            "balance": float(account.balance)
        }
    }), 200


@bp.route("/<int:account_id>", methods=["DELETE"])
def delete_account(account_id):
    """Delete (deactivate) an account."""
    account = FinancialAccount.query.filter_by(
        id=account_id,
        user_id=g.user.id
    ).first()
    
    if not account:
        return jsonify({"error": "Account not found"}), 404
    
    # Soft delete - just deactivate
    account.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Account deactivated successfully"}), 200


@bp.route("/overview", methods=["GET"])
def get_overview():
    """Get multi-account financial overview dashboard."""
    accounts = FinancialAccount.query.filter_by(
        user_id=g.user.id,
        is_active=True
    ).all()
    
    if not accounts:
        return jsonify({
            "overview": {
                "total_balance": 0,
                "total_accounts": 0,
                "accounts": [],
                "by_type": {},
                "by_currency": {}
            }
        }), 200
    
    # Calculate totals
    total_balance = sum(float(a.balance) for a in accounts)
    
    # Group by account type
    by_type = {}
    for a in accounts:
        if a.account_type not in by_type:
            by_type[a.account_type] = {"count": 0, "balance": 0}
        by_type[a.account_type]["count"] += 1
        by_type[a.account_type]["balance"] += float(a.balance)
    
    # Group by currency
    by_currency = {}
    for a in accounts:
        if a.currency not in by_currency:
            by_currency[a.currency] = {"count": 0, "balance": 0}
        by_currency[a.currency]["count"] += 1
        by_currency[a.currency]["balance"] += float(a.balance)
    
    # Get recent spending summary (last 30 days)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    recent_expenses = db.session.query(
        func.sum(Expense.amount)
    ).filter(
        Expense.user_id == g.user.id,
        Expense.spent_at >= thirty_days_ago
    ).scalar() or 0
    
    # Get upcoming bills
    upcoming_bills = Bill.query.filter(
        Bill.user_id == g.user.id,
        Bill.active == True,
        Bill.next_due_date >= datetime.now().date()
    ).count()
    
    return jsonify({
        "overview": {
            "total_balance": round(total_balance, 2),
            "total_accounts": len(accounts),
            "accounts": [{
                "id": a.id,
                "name": a.name,
                "account_type": a.account_type,
                "balance": float(a.balance),
                "currency": a.currency,
                "color": a.color,
                "icon": a.icon
            } for a in accounts],
            "by_type": by_type,
            "by_currency": by_currency,
            "recent_expenses_30d": float(recent_expenses),
            "upcoming_bills_count": upcoming_bills
        }
    }), 200
