from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, extract
from ..extensions import db
from ..models import Expense, Category, Bill
import logging

bp = Blueprint("accounts", __name__)
logger = logging.getLogger("finmind.accounts")

# In-memory store (would be DB table in production)
_accounts_store = {}
_counter = [0]


def _next_id():
    _counter[0] += 1
    return _counter[0]


@bp.route("/", methods=["GET"])
@jwt_required()
def list_accounts():
    uid = str(get_jwt_identity())
    accounts = _accounts_store.get(uid, [])
    return jsonify({"accounts": accounts})


@bp.route("/", methods=["POST"])
@jwt_required()
def create_account():
    uid = str(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    account = {
        "id": _next_id(),
        "name": name,
        "account_type": data.get("account_type", "checking"),
        "currency": data.get("currency", "USD"),
        "color": data.get("color", "#3B82F6"),
        "icon": data.get("icon", "wallet"),
        "is_default": data.get("is_default", False),
        "created_at": date.today().isoformat(),
    }

    if account["is_default"]:
        for a in _accounts_store.get(uid, []):
            a["is_default"] = False

    if not _accounts_store.get(uid) and not account["is_default"]:
        account["is_default"] = True

    _accounts_store.setdefault(uid, []).append(account)
    logger.info("Account created user=%s account_id=%s", uid, account["id"])
    return jsonify(account), 201


@bp.route("/<int:account_id>", methods=["PUT"])
@jwt_required()
def update_account(account_id):
    uid = str(get_jwt_identity())
    data = request.get_json() or {}
    for a in _accounts_store.get(uid, []):
        if a["id"] == account_id:
            for key in ["name", "account_type", "currency", "color", "icon"]:
                if key in data:
                    a[key] = data[key]
            if data.get("is_default"):
                for other in _accounts_store[uid]:
                    other["is_default"] = False
                a["is_default"] = True
            return jsonify(a)
    return jsonify(error="Account not found"), 404


@bp.route("/<int:account_id>", methods=["DELETE"])
@jwt_required()
def delete_account(account_id):
    uid = str(get_jwt_identity())
    accounts = _accounts_store.get(uid, [])
    was_default = any(a["id"] == account_id and a.get("is_default") for a in accounts)
    _accounts_store[uid] = [a for a in accounts if a["id"] != account_id]
    if was_default and _accounts_store[uid]:
        _accounts_store[uid][0]["is_default"] = True
    return jsonify(status="deleted")


@bp.route("/overview")
@jwt_required()
def multi_account_overview():
    uid = int(get_jwt_identity())
    uid_str = str(uid)
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    year, month = map(int, ym.split("-"))
    accounts = _accounts_store.get(uid_str, [])

    if not accounts:
        # Auto-create default account
        default = {
            "id": _next_id(),
            "name": "Main Account",
            "account_type": "checking",
            "currency": "USD",
            "color": "#3B82F6",
            "icon": "wallet",
            "is_default": True,
            "created_at": date.today().isoformat(),
        }
        accounts = [default]
        _accounts_store[uid_str] = accounts

    # Get monthly stats
    income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    # Category breakdown
    cat_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    # Upcoming bills
    bills = Bill.query.filter(
        Bill.user_id == uid,
        Bill.active.is_(True),
        Bill.next_due_date >= date.today(),
    ).order_by(Bill.next_due_date.asc()).limit(5).all()

    # Build per-account view (distribute evenly for now)
    per_account = []
    n = len(accounts)
    for acc in accounts:
        share = 1.0 / n if n > 0 else 1.0
        per_account.append({
            "account": acc,
            "income": round(income * share, 2),
            "expenses": round(expenses * share, 2),
            "net_flow": round((income - expenses) * share, 2),
        })

    return jsonify({
        "period": ym,
        "accounts": per_account,
        "combined": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
        },
        "category_breakdown": [
            {"category_id": r.category_id, "name": r.name, "total": float(r.total)}
            for r in cat_rows
        ],
        "upcoming_bills": [
            {
                "name": b.name,
                "amount": float(b.amount),
                "due_date": b.next_due_date.isoformat(),
            }
            for b in bills
        ],
    })
