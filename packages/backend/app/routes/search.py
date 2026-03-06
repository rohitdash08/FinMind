"""Advanced search across transactions and bills.

Provides a unified ``/search`` endpoint that queries both expenses and bills
with flexible filter parameters: free-text query, category, amount range,
date range, expense type, and result type selection.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_
from ..extensions import db
from ..models import Bill, Category, Expense
import logging

bp = Blueprint("search", __name__)
logger = logging.getLogger("finmind.search")

_MAX_PAGE_SIZE = 200


@bp.get("")
@jwt_required()
def search():
    """Search across expenses and bills.

    Query parameters
    ----------------
    q : str, optional
        Free-text search term matched against expense descriptions/notes,
        bill names, and category names (case-insensitive substring match).
    category_id : int, optional
        Filter expenses by category id.
    category : str, optional
        Filter expenses whose category *name* contains this substring
        (case-insensitive).  Ignored when ``category_id`` is provided.
    amount_min : decimal, optional
        Minimum amount (inclusive).
    amount_max : decimal, optional
        Maximum amount (inclusive).
    from : str (YYYY-MM-DD), optional
        Start date (inclusive) — applies to ``spent_at`` for expenses and
        ``next_due_date`` for bills.
    to : str (YYYY-MM-DD), optional
        End date (inclusive).
    expense_type : str, optional
        Filter expenses by type (e.g. EXPENSE, INCOME).
    type : str, optional
        Restrict results to ``expenses``, ``bills``, or ``all`` (default).
    sort : str, optional
        Sort field — ``date`` (default), ``amount``, or ``name``.
    order : str, optional
        ``asc`` or ``desc`` (default).
    page : int, optional
        Page number (1-indexed, default 1).
    page_size : int, optional
        Results per page (default 50, max 200).

    Returns
    -------
    JSON with ``results`` (list), ``total`` count, ``page``, ``page_size``,
    and per-type counts ``expense_count`` / ``bill_count``.
    """

    uid = int(get_jwt_identity())

    # --- Parse common params ---------------------------------------------------
    q = (request.args.get("q") or "").strip()
    category_id = _parse_int(request.args.get("category_id"))
    category_name = (request.args.get("category") or "").strip()
    amount_min = _parse_decimal(request.args.get("amount_min"))
    amount_max = _parse_decimal(request.args.get("amount_max"))
    from_date = _parse_date(request.args.get("from"))
    to_date = _parse_date(request.args.get("to"))
    expense_type = (request.args.get("expense_type") or "").strip().upper() or None
    result_type = (request.args.get("type") or "all").strip().lower()
    sort_field = (request.args.get("sort") or "date").strip().lower()
    order = (request.args.get("order") or "desc").strip().lower()

    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(_MAX_PAGE_SIZE, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination parameters"), 400

    if result_type not in ("all", "expenses", "bills"):
        return jsonify(error="type must be 'all', 'expenses', or 'bills'"), 400
    if sort_field not in ("date", "amount", "name"):
        return jsonify(error="sort must be 'date', 'amount', or 'name'"), 400
    if order not in ("asc", "desc"):
        return jsonify(error="order must be 'asc' or 'desc'"), 400

    # --- Resolve category name → ids (if needed) ------------------------------
    matching_cat_ids: list[int] | None = None
    if category_id is not None:
        matching_cat_ids = [category_id]
    elif category_name:
        cats = (
            db.session.query(Category.id)
            .filter(Category.user_id == uid, Category.name.ilike(f"%{category_name}%"))
            .all()
        )
        matching_cat_ids = [c.id for c in cats]

    # --- Build results ---------------------------------------------------------
    expense_results: list[dict] = []
    bill_results: list[dict] = []

    if result_type in ("all", "expenses"):
        expense_results = _search_expenses(
            uid, q, matching_cat_ids, amount_min, amount_max,
            from_date, to_date, expense_type,
        )

    if result_type in ("all", "bills"):
        bill_results = _search_bills(
            uid, q, amount_min, amount_max, from_date, to_date,
        )

    # --- Merge, sort, paginate -------------------------------------------------
    combined = expense_results + bill_results
    combined = _sort_results(combined, sort_field, order)

    total = len(combined)
    start = (page - 1) * page_size
    page_items = combined[start: start + page_size]

    logger.info(
        "Search user=%s q=%r total=%s (expenses=%s bills=%s)",
        uid, q, total, len(expense_results), len(bill_results),
    )

    return jsonify(
        results=page_items,
        total=total,
        page=page,
        page_size=page_size,
        expense_count=len(expense_results),
        bill_count=len(bill_results),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _search_expenses(
    uid: int,
    q: str,
    cat_ids: list[int] | None,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
    from_date: date | None,
    to_date: date | None,
    expense_type: str | None,
) -> list[dict]:
    """Return matching expenses as dicts with ``result_type='expense'``."""
    query = db.session.query(Expense).filter(Expense.user_id == uid)

    if q:
        like = f"%{q}%"
        # Also search through category names via a subquery
        cat_subq = (
            db.session.query(Category.id)
            .filter(Category.user_id == uid, Category.name.ilike(like))
            .subquery()
        )
        query = query.filter(
            or_(
                Expense.notes.ilike(like),
                Expense.category_id.in_(cat_subq),
            )
        )

    if cat_ids is not None:
        if not cat_ids:
            return []  # category name matched nothing
        query = query.filter(Expense.category_id.in_(cat_ids))

    if amount_min is not None:
        query = query.filter(Expense.amount >= amount_min)
    if amount_max is not None:
        query = query.filter(Expense.amount <= amount_max)
    if from_date:
        query = query.filter(Expense.spent_at >= from_date)
    if to_date:
        query = query.filter(Expense.spent_at <= to_date)
    if expense_type:
        query = query.filter(Expense.expense_type == expense_type)

    rows = query.order_by(Expense.spent_at.desc()).limit(_MAX_PAGE_SIZE).all()

    # Pre-fetch category names for matched expenses
    cat_ids_needed = {e.category_id for e in rows if e.category_id}
    cat_map: dict[int, str] = {}
    if cat_ids_needed:
        cats = (
            db.session.query(Category)
            .filter(Category.id.in_(cat_ids_needed))
            .all()
        )
        cat_map = {c.id: c.name for c in cats}

    return [
        {
            "result_type": "expense",
            "id": e.id,
            "description": e.notes or "",
            "amount": float(e.amount),
            "currency": e.currency,
            "date": e.spent_at.isoformat(),
            "expense_type": e.expense_type,
            "category_id": e.category_id,
            "category_name": cat_map.get(e.category_id, ""),
        }
        for e in rows
    ]


def _search_bills(
    uid: int,
    q: str,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
    from_date: date | None,
    to_date: date | None,
) -> list[dict]:
    """Return matching bills as dicts with ``result_type='bill'``."""
    query = db.session.query(Bill).filter(Bill.user_id == uid, Bill.active == True)  # noqa: E712

    if q:
        query = query.filter(Bill.name.ilike(f"%{q}%"))

    if amount_min is not None:
        query = query.filter(Bill.amount >= amount_min)
    if amount_max is not None:
        query = query.filter(Bill.amount <= amount_max)
    if from_date:
        query = query.filter(Bill.next_due_date >= from_date)
    if to_date:
        query = query.filter(Bill.next_due_date <= to_date)

    rows = query.order_by(Bill.next_due_date.desc()).limit(_MAX_PAGE_SIZE).all()

    return [
        {
            "result_type": "bill",
            "id": b.id,
            "description": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "autopay_enabled": b.autopay_enabled,
        }
        for b in rows
    ]


def _sort_results(items: list[dict], field: str, order: str) -> list[dict]:
    """Sort combined results by the chosen field."""
    reverse = order == "desc"
    if field == "date":
        return sorted(items, key=lambda x: x.get("date", ""), reverse=reverse)
    if field == "amount":
        return sorted(items, key=lambda x: x.get("amount", 0), reverse=reverse)
    if field == "name":
        return sorted(items, key=lambda x: x.get("description", "").lower(), reverse=reverse)
    return items


def _parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
