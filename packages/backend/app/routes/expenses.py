import calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Expense, RecurringCadence, RecurringExpense, User
from ..request_utils import get_json_object
from ..services.cache import cache_delete_patterns, monthly_summary_key
from ..services import expense_import
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
    user = db.session.get(User, uid)
    data = get_json_object()
    if data is None:
        return jsonify(error="json body must be an object"), 400
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="invalid amount"), 400
    category_id = _parse_category_id(data.get("category_id"))
    if (
        "category_id" in data
        and data.get("category_id") not in (None, "", "null")
        and category_id is None
    ):
        return jsonify(error="invalid category_id"), 400
    raw_date = data.get("date") or data.get("spent_at")
    spent_at = _parse_date(raw_date)
    if raw_date and spent_at is None:
        return jsonify(error="invalid date"), 400
    description = str(data.get("description") or data.get("notes") or "").strip()
    if not description:
        return jsonify(error="description required"), 400
    e = Expense(
        user_id=uid,
        amount=amount,
        currency=(data.get("currency") or (user.preferred_currency if user else "INR")),
        expense_type=str(data.get("expense_type") or "EXPENSE").upper(),
        category_id=category_id,
        notes=description,
        spent_at=spent_at or date.today(),
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
    return jsonify(_expense_to_dict(e)), 201


@bp.get("/recurring")
@jwt_required()
def list_recurring_expenses():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=uid, active=True)
        .order_by(RecurringExpense.created_at.desc())
        .all()
    )
    return jsonify([_recurring_to_dict(r) for r in items])


@bp.post("/recurring")
@jwt_required()
def create_recurring_expense():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = get_json_object()
    if data is None:
        return jsonify(error="json body must be an object"), 400
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="invalid amount"), 400
    category_id = _parse_category_id(data.get("category_id"))
    if (
        "category_id" in data
        and data.get("category_id") not in (None, "", "null")
        and category_id is None
    ):
        return jsonify(error="invalid category_id"), 400
    description = str(data.get("description") or data.get("notes") or "").strip()
    if not description:
        return jsonify(error="description required"), 400
    cadence = _parse_recurring_cadence(data.get("cadence"))
    if cadence is None:
        return jsonify(error="invalid cadence"), 400
    start_raw = data.get("start_date")
    if not start_raw:
        return jsonify(error="start_date required"), 400
    try:
        start_date = date.fromisoformat(str(start_raw))
    except (TypeError, ValueError):
        return jsonify(error="invalid start_date"), 400
    end_date = None
    if data.get("end_date"):
        try:
            end_date = date.fromisoformat(str(data.get("end_date")))
        except (TypeError, ValueError):
            return jsonify(error="invalid end_date"), 400
        if end_date < start_date:
            return jsonify(error="end_date must be on or after start_date"), 400
    recurring = RecurringExpense(
        user_id=uid,
        category_id=category_id,
        amount=amount,
        currency=(data.get("currency") or (user.preferred_currency if user else "INR")),
        expense_type=str(data.get("expense_type") or "EXPENSE").upper(),
        notes=description,
        cadence=RecurringCadence(cadence),
        start_date=start_date,
        end_date=end_date,
    )
    db.session.add(recurring)
    db.session.commit()
    return jsonify(_recurring_to_dict(recurring)), 201


@bp.post("/recurring/<int:recurring_id>/generate")
@jwt_required()
def generate_recurring_expenses(recurring_id: int):
    uid = int(get_jwt_identity())
    recurring = db.session.get(RecurringExpense, recurring_id)
    if not recurring or recurring.user_id != uid:
        return jsonify(error="not found"), 404
    payload = get_json_object()
    if payload is None:
        return jsonify(error="json body must be an object"), 400
    through_raw = payload.get("through_date")
    if not through_raw:
        return jsonify(error="through_date required"), 400
    try:
        through_date = date.fromisoformat(str(through_raw))
    except (TypeError, ValueError):
        return jsonify(error="invalid through_date"), 400
    window_end = through_date
    if recurring.end_date and recurring.end_date < window_end:
        window_end = recurring.end_date
    if window_end < recurring.start_date:
        return jsonify(inserted=0), 200

    inserted = 0
    touched_months: set[str] = set()
    at = recurring.start_date
    while at <= window_end:
        exists = (
            db.session.query(Expense.id)
            .filter_by(
                user_id=uid,
                source_recurring_id=recurring.id,
                spent_at=at,
            )
            .first()
        )
        if not exists:
            db.session.add(
                Expense(
                    user_id=uid,
                    category_id=recurring.category_id,
                    amount=recurring.amount,
                    currency=recurring.currency,
                    expense_type=recurring.expense_type,
                    notes=recurring.notes,
                    spent_at=at,
                    source_recurring_id=recurring.id,
                )
            )
            inserted += 1
            touched_months.add(at.strftime("%Y-%m"))
        at = _advance_recurrence_date(at, recurring.cadence.value)
    db.session.commit()
    for ym in touched_months:
        _invalidate_expense_cache(uid, ym + "-01")
    return jsonify(inserted=inserted), 200


@bp.patch("/<int:expense_id>")
@jwt_required()
def update_expense(expense_id: int):
    uid = int(get_jwt_identity())
    e = db.session.get(Expense, expense_id)
    if not e or e.user_id != uid:
        return jsonify(error="not found"), 404
    data = get_json_object()
    if data is None:
        return jsonify(error="json body must be an object"), 400
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
        category_id = _parse_category_id(data.get("category_id"))
        if data.get("category_id") not in (None, "", "null") and category_id is None:
            return jsonify(error="invalid category_id"), 400
        e.category_id = category_id
    if "description" in data or "notes" in data:
        description = str(data.get("description") or data.get("notes") or "").strip()
        if not description:
            return jsonify(error="description required"), 400
        e.notes = description
    if "date" in data or "spent_at" in data:
        raw_date = data.get("date") or data.get("spent_at")
        spent_at = _parse_date(raw_date)
        if spent_at is None:
            return jsonify(error="invalid date"), 400
        e.spent_at = spent_at
    db.session.commit()
    _invalidate_expense_cache(uid, e.spent_at.isoformat())
    return jsonify(_expense_to_dict(e))


@bp.delete("/<int:expense_id>")
@jwt_required()
def delete_expense(expense_id: int):
    uid = int(get_jwt_identity())
    e = db.session.get(Expense, expense_id)
    if not e or e.user_id != uid:
        return jsonify(error="not found"), 404
    spent_at = e.spent_at.isoformat()
    db.session.delete(e)
    db.session.commit()
    _invalidate_expense_cache(uid, spent_at)
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
    except Exception:  # pragma: no cover
        logger.exception("Import preview failed user=%s", uid)
        return jsonify(error="failed to parse statement"), 500
    duplicates = sum(1 for t in transactions if _is_duplicate(uid, t))
    return jsonify(
        total=len(transactions), duplicates=duplicates, transactions=transactions
    )


@bp.post("/import/commit")
@jwt_required()
def import_commit():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = get_json_object()
    if data is None:
        return jsonify(error="json body must be an object"), 400
    rows = data.get("transactions") or []
    if not isinstance(rows, list) or not rows:
        return jsonify(error="transactions required"), 400
    try:
        transactions = expense_import.normalize_import_rows(rows)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not transactions:
        return jsonify(error="no valid transactions"), 400
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
            currency=t.get("currency") or (user.preferred_currency if user else "INR"),
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


def _recurring_to_dict(r: RecurringExpense) -> dict:
    return {
        "id": r.id,
        "amount": float(r.amount),
        "currency": r.currency,
        "expense_type": r.expense_type,
        "category_id": r.category_id,
        "description": r.notes,
        "cadence": r.cadence.value,
        "start_date": r.start_date.isoformat(),
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "active": r.active,
    }


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _parse_category_id(raw) -> int | None:
    if raw in (None, "", "null"):
        return None
    try:
        category_id = int(raw)
    except (TypeError, ValueError):
        return None
    if category_id <= 0:
        return None
    return category_id


def _parse_recurring_cadence(raw: str | None) -> str | None:
    val = str(raw or "").upper().strip()
    if val in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}:
        return val
    return None


def _advance_recurrence_date(at: date, cadence: str) -> date:
    if cadence == RecurringCadence.DAILY.value:
        return at + timedelta(days=1)
    if cadence == RecurringCadence.WEEKLY.value:
        return at + timedelta(days=7)
    if cadence == RecurringCadence.MONTHLY.value:
        year = at.year + (1 if at.month == 12 else 0)
        month = 1 if at.month == 12 else at.month + 1
        day = min(at.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    year = at.year + 1
    day = min(at.day, calendar.monthrange(year, at.month)[1])
    return date(year, at.month, day)


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
