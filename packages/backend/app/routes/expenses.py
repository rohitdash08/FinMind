from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Expense
from ..services.cache import cache_delete_patterns, monthly_summary_key
from ..services import expense_import
from ..services.event_emitter import emit
import logging

bp = Blueprint("expenses", __name__)
logger = logging.getLogger("finmind.expenses")


@bp.get("")
@jwt_required()
def list_expenses():
    uid = int(get_jwt_identity())
    q = db.session.query(Expense).filter_by(user_id=uid)
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    search = (request.args.get("search") or "").strip()
    category_id = request.args.get("category_id")
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(200, max(1, int(request.args.get("page_size", "200"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    try:
        if from_date:
            q = q.filter(Expense.spent_at >= date.fromisoformat(from_date))
        if to_date:
            q = q.filter(Expense.spent_at <= date.fromisoformat(to_date))
        if category_id:
            q = q.filter(Expense.category_id == int(category_id))
    except ValueError:
        return jsonify(error="invalid filter values"), 400
    if search:
        q = q.filter(Expense.notes.ilike(f"%{search}%"))

    items = (
        q.order_by(Expense.spent_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    logger.info("List expenses user=%s count=%s", uid, len(items))
    data = [_expense_to_dict(e) for e in items]
    return jsonify(data)


@bp.post("")
@jwt_required()
def create_expense():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="invalid amount"), 400
    raw_date = data.get("date") or data.get("spent_at")
    description = (data.get("description") or data.get("notes") or "").strip()
    if not description:
        return jsonify(error="description required"), 400
    e = Expense(
        user_id=uid,
        amount=amount,
        currency=data.get("currency", "USD"),
        expense_type=str(data.get("expense_type") or "EXPENSE").upper(),
        category_id=data.get("category_id"),
        notes=description,
        spent_at=date.fromisoformat(raw_date) if raw_date else date.today(),
    )
    db.session.add(e)
    db.session.commit()
    logger.info("Created expense id=%s user=%s amount=%s", e.id, uid, e.amount)
    # Invalidate caches
    cache_delete_patterns(
        [
            monthly_summary_key(uid, e.spent_at.strftime("%Y-%m")),
            f"insights:{uid}:*",
        ]
    )
    # Emit webhook event
    emit(uid, "expense.created", _expense_to_dict(e))
    return jsonify(_expense_to_dict(e)), 201


@bp.patch("/<int:expense_id>")
@jwt_required()
def update_expense(expense_id: int):
    uid = int(get_jwt_identity())
    e = db.session.get(Expense, expense_id)
    if not e or e.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "amount" in data:
        amount = _parse_amount(data.get("amount"))
        if amount is None:
            return jsonify(error="invalid amount"), 400
        e.amount = amount
    if "currency" in data:
        e.currency = str(data.get("currency") or "USD")[:10]
    if "expense_type" in data:
        e.expense_type = str(data.get("expense_type") or "EXPENSE").upper()
    if "category_id" in data:
        e.category_id = data.get("category_id")
    if "description" in data or "notes" in data:
        description = (data.get("description") or data.get("notes") or "").strip()
        if not description:
            return jsonify(error="description required"), 400
        e.notes = description
    if "date" in data or "spent_at" in data:
        raw_date = data.get("date") or data.get("spent_at")
        e.spent_at = date.fromisoformat(raw_date)
    db.session.commit()
    _invalidate_expense_cache(uid, e.spent_at.isoformat())
    # Emit webhook event
    emit(uid, "expense.updated", _expense_to_dict(e))
    return jsonify(_expense_to_dict(e))


@bp.delete("/<int:expense_id>")
@jwt_required()
def delete_expense(expense_id: int):
    uid = int(get_jwt_identity())
    e = db.session.get(Expense, expense_id)
    if not e or e.user_id != uid:
        return jsonify(error="not found"), 404
    expense_data = _expense_to_dict(e)
    spent_at = e.spent_at.isoformat()
    db.session.delete(e)
    db.session.commit()
    _invalidate_expense_cache(uid, spent_at)
    # Emit webhook event
    emit(uid, "expense.deleted", expense_data)
    return jsonify(message="deleted")


@bp.post("/import/preview")
@jwt_required()
def import_preview():
    uid = int(get_jwt_identity())
    file = request.files.get("file")
    if not file:
        return jsonify(error="file required"), 400
    raw = file.read()
    try:
        rows = expense_import.extract_transactions_from_statement(
            filename=file.filename or "",
            content_type=file.content_type,
            data=raw,
            gemini_api_key=current_app.config.get("GEMINI_API_KEY"),
            gemini_model=current_app.config.get("GEMINI_MODEL", "gemini-1.5-flash"),
        )
        transactions = expense_import.normalize_import_rows(rows)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:  # pragma: no cover
        logger.exception("Import preview failed user=%s", uid)
        return jsonify(error=f"failed to parse statement: {exc}"), 500
    duplicates = sum(1 for t in transactions if _is_duplicate(uid, t))
    return jsonify(
        total=len(transactions), duplicates=duplicates, transactions=transactions
    )


@bp.post("/import/commit")
@jwt_required()
def import_commit():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    rows = data.get("transactions") or []
    if not isinstance(rows, list) or not rows:
        return jsonify(error="transactions required"), 400
    transactions = expense_import.normalize_import_rows(rows)
    inserted = 0
    duplicates = 0
    touched_months: set[str] = set()
    for t in transactions:
        if _is_duplicate(uid, t):
            duplicates += 1
            continue
        expense = Expense(
            user_id=uid,
            amount=t["amount"],
            currency=t.get("currency", "USD"),
            expense_type=str(t.get("expense_type") or "EXPENSE").upper(),
            category_id=t.get("category_id"),
            notes=t["description"],
            spent_at=date.fromisoformat(t["date"]),
        )
        db.session.add(expense)
        inserted += 1
        touched_months.add(t["date"][:7])
    db.session.commit()
    for ym in touched_months:
        _invalidate_expense_cache(uid, ym + "-01")
    # Emit webhook event for import completion
    emit(uid, "import.completed", {"inserted": inserted, "duplicates": duplicates})
    return jsonify(inserted=inserted, duplicates=duplicates), 201


def _expense_to_dict(e: Expense) -> dict:
    return {
        "id": e.id,
        "amount": float(e.amount),
        "currency": e.currency,
        "category_id": e.category_id,
        "expense_type": e.expense_type,
        "description": e.notes or "",
        "date": e.spent_at.isoformat(),
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_duplicate(uid: int, row: dict) -> bool:
    amount = _parse_amount(row["amount"])
    if amount is None:
        return False
    return (
        db.session.query(Expense)
        .filter_by(
            user_id=uid,
            spent_at=date.fromisoformat(row["date"]),
            amount=amount,
            notes=row["description"],
        )
        .first()
        is not None
    )


def _invalidate_expense_cache(uid: int, at: str):
    ym = at[:7]
    cache_delete_patterns(
        [
            monthly_summary_key(uid, ym),
            f"insights:{uid}:*",
            f"user:{uid}:dashboard_summary:*",
        ]
    )
