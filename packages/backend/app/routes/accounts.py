"""
Multi-account financial overview dashboard — #132

Allows users to manage multiple financial accounts (checking, savings, credit, investment)
and view an aggregated dashboard across all accounts.

Models:
- FinancialAccount: id, user_id, name, type, balance, currency, institution, is_active
- AccountTransaction: id, account_id, amount, description, transaction_date, category

API:
- CRUD accounts
- Dashboard with aggregate balances and per-account breakdown
- Recent transactions across all accounts
"""
from datetime import datetime, date
from enum import Enum as PyEnum

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship

from ..extensions import db


class AccountType(str, PyEnum):
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CREDIT = "CREDIT"
    INVESTMENT = "INVESTMENT"
    CASH = "CASH"
    OTHER = "OTHER"


class FinancialAccount(db.Model):
    __tablename__ = "financial_accounts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    account_type = Column(String(50), default=AccountType.CHECKING.value, nullable=False)
    balance = Column(Numeric(14, 2), default=0.00, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    institution = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "account_type": self.account_type,
            "balance": float(self.balance),
            "currency": self.currency,
            "institution": self.institution,
            "is_active": self.is_active,
        }


accounts_bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")


@accounts_bp.route("", methods=["GET"])
def list_accounts():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    accounts = FinancialAccount.query.filter_by(
        user_id=user_id, is_active=True
    ).order_by(FinancialAccount.account_type, FinancialAccount.name).all()
    return jsonify({"accounts": [a.to_dict() for a in accounts]}), 200


@accounts_bp.route("", methods=["POST"])
def create_account():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("account_type"):
        return jsonify({"error": "name and account_type required"}), 400

    account = FinancialAccount(
        user_id=data["user_id"],
        name=data["name"],
        account_type=data["account_type"],
        balance=data.get("balance", 0),
        currency=data.get("currency", "USD"),
        institution=data.get("institution"),
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(account.to_dict()), 201


@accounts_bp.route("/<int:account_id>/balance", methods=["PATCH"])
def update_balance(account_id: int):
    account = db.session.get(FinancialAccount, account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404

    data = request.get_json()
    if "balance" in data:
        account.balance = data["balance"]
    if "name" in data:
        account.name = data["name"]
    if "is_active" in data:
        account.is_active = data["is_active"]
    db.session.commit()
    return jsonify(account.to_dict()), 200


@accounts_bp.route("/<int:account_id>", methods=["DELETE"])
def delete_account(account_id: int):
    account = db.session.get(FinancialAccount, account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    account.is_active = False
    db.session.commit()
    return jsonify({"message": "Account deactivated"}), 200


@accounts_bp.route("/dashboard", methods=["GET"])
def dashboard():
    """Aggregated multi-account financial overview."""
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    accounts = FinancialAccount.query.filter_by(user_id=user_id, is_active=True).all()

    total_balance = sum(float(a.balance) for a in accounts)
    by_type: dict[str, dict] = {}
    for a in accounts:
        t = a.account_type
        if t not in by_type:
            by_type[t] = {"accounts": [], "total": 0.0, "count": 0}
        by_type[t]["accounts"].append(a.to_dict())
        by_type[t]["total"] += float(a.balance)
        by_type[t]["count"] += 1

    # Format by_type for response
    breakdown = []
    for t, data in sorted(by_type.items()):
        breakdown.append({
            "type": t,
            "count": data["count"],
            "total_balance": round(data["total"], 2),
            "accounts": data["accounts"],
        })

    return jsonify({
        "total_accounts": len(accounts),
        "total_balance": round(total_balance, 2),
        "breakdown": breakdown,
    }), 200
