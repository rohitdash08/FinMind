"""Advanced search across transactions and bills.

Provides unified search across expenses, bills, and recurring expenses
with support for:
  - Full-text search on notes/descriptions
  - Category filtering
  - Amount range filtering
  - Date range filtering
  - Expense type filtering
  - Sort options
  - Pagination
  - Search across multiple entity types
"""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, and_, func

from ..extensions import db
from ..models import Expense, Bill, Category, RecurringExpense

logger = logging.getLogger("finmind.search")


def advanced_search(
    user_id: int,
    query: str | None = None,
    category_id: int | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    expense_type: str | None = None,
    entity_types: list[str] | None = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Search across transactions, bills, and recurring expenses.

    Args:
        user_id: The user ID to search for.
        query: Text to search in notes/names (case-insensitive).
        category_id: Filter by category ID.
        amount_min: Minimum amount filter.
        amount_max: Maximum amount filter.
        date_from: Start date filter.
        date_to: End date filter.
        expense_type: Filter by type (EXPENSE or INCOME).
        entity_types: List of entity types to search (expenses, bills, recurring).
        sort_by: Sort field (date, amount, name).
        sort_order: Sort direction (asc, desc).
        page: Page number (1-based).
        page_size: Results per page.

    Returns:
        Dict with results, total count, and pagination info.
    """
    if entity_types is None:
        entity_types = ["expenses", "bills", "recurring"]

    results = []
    total_count = 0

    if "expenses" in entity_types:
        exp_results, exp_count = _search_expenses(
            user_id, query, category_id, amount_min, amount_max,
            date_from, date_to, expense_type, sort_by, sort_order,
        )
        results.extend(exp_results)
        total_count += exp_count

    if "bills" in entity_types:
        bill_results, bill_count = _search_bills(
            user_id, query, amount_min, amount_max,
            date_from, date_to, sort_by, sort_order,
        )
        results.extend(bill_results)
        total_count += bill_count

    if "recurring" in entity_types:
        rec_results, rec_count = _search_recurring(
            user_id, query, category_id, amount_min, amount_max,
            expense_type, sort_by, sort_order,
        )
        results.extend(rec_results)
        total_count += rec_count

    # Sort combined results
    results = _sort_results(results, sort_by, sort_order)

    # Paginate
    offset = (page - 1) * page_size
    paginated = results[offset : offset + page_size]

    logger.info(
        "Search user=%d query=%s results=%d",
        user_id, query, total_count,
    )

    return {
        "results": paginated,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
        "has_more": offset + page_size < total_count,
    }


def search_suggestions(user_id: int, prefix: str, limit: int = 10) -> list[dict]:
    """Get search suggestions based on a prefix.

    Searches across expense notes, bill names, and category names for
    autocomplete suggestions.
    """
    if not prefix or len(prefix) < 2:
        return []

    suggestions = []
    pattern = f"%{prefix}%"

    # Search expense notes
    notes = (
        db.session.query(Expense.notes)
        .filter(
            Expense.user_id == user_id,
            Expense.notes.ilike(pattern),
        )
        .distinct()
        .limit(limit)
        .all()
    )
    for (note,) in notes:
        if note:
            suggestions.append({"text": note, "type": "expense"})

    # Search bill names
    bills = (
        db.session.query(Bill.name)
        .filter(
            Bill.user_id == user_id,
            Bill.name.ilike(pattern),
        )
        .distinct()
        .limit(limit)
        .all()
    )
    for (name,) in bills:
        suggestions.append({"text": name, "type": "bill"})

    # Search category names
    cats = (
        db.session.query(Category.name)
        .filter(
            Category.user_id == user_id,
            Category.name.ilike(pattern),
        )
        .distinct()
        .limit(limit)
        .all()
    )
    for (name,) in cats:
        suggestions.append({"text": name, "type": "category"})

    # Deduplicate and limit
    seen = set()
    unique = []
    for s in suggestions:
        key = s["text"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)
            if len(unique) >= limit:
                break

    return unique


def get_search_stats(user_id: int) -> dict:
    """Get search-related statistics for a user.

    Returns counts of expenses, bills, categories, and recurring expenses
    to help users understand their searchable data.
    """
    expense_count = (
        db.session.query(func.count(Expense.id))
        .filter_by(user_id=user_id)
        .scalar()
    )
    bill_count = (
        db.session.query(func.count(Bill.id))
        .filter_by(user_id=user_id)
        .scalar()
    )
    category_count = (
        db.session.query(func.count(Category.id))
        .filter_by(user_id=user_id)
        .scalar()
    )
    recurring_count = (
        db.session.query(func.count(RecurringExpense.id))
        .filter_by(user_id=user_id)
        .scalar()
    )
    date_range = (
        db.session.query(
            func.min(Expense.spent_at),
            func.max(Expense.spent_at),
        )
        .filter_by(user_id=user_id)
        .first()
    )

    return {
        "expense_count": expense_count or 0,
        "bill_count": bill_count or 0,
        "category_count": category_count or 0,
        "recurring_count": recurring_count or 0,
        "total_searchable": (expense_count or 0) + (bill_count or 0) + (recurring_count or 0),
        "date_range": {
            "earliest": date_range[0].isoformat() if date_range and date_range[0] else None,
            "latest": date_range[1].isoformat() if date_range and date_range[1] else None,
        },
    }


# ─── Internal search functions ──────────────────────────────────────────


def _search_expenses(
    user_id, query, category_id, amount_min, amount_max,
    date_from, date_to, expense_type, sort_by, sort_order,
) -> tuple[list[dict], int]:
    """Search expenses with filters."""
    q = db.session.query(Expense).filter_by(user_id=user_id)

    if query:
        q = q.filter(Expense.notes.ilike(f"%{query}%"))
    if category_id:
        q = q.filter(Expense.category_id == category_id)
    if amount_min is not None:
        q = q.filter(Expense.amount >= Decimal(str(amount_min)))
    if amount_max is not None:
        q = q.filter(Expense.amount <= Decimal(str(amount_max)))
    if date_from:
        q = q.filter(Expense.spent_at >= date_from)
    if date_to:
        q = q.filter(Expense.spent_at <= date_to)
    if expense_type:
        q = q.filter(Expense.expense_type == expense_type.upper())

    count = q.count()
    expenses = q.all()

    results = []
    for e in expenses:
        cat = db.session.get(Category, e.category_id) if e.category_id else None
        results.append({
            "id": e.id,
            "type": "expense",
            "name": e.notes or "",
            "amount": float(e.amount),
            "currency": e.currency,
            "category": cat.name if cat else None,
            "category_id": e.category_id,
            "date": e.spent_at.isoformat() if e.spent_at else None,
            "expense_type": e.expense_type,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return results, count


def _search_bills(
    user_id, query, amount_min, amount_max,
    date_from, date_to, sort_by, sort_order,
) -> tuple[list[dict], int]:
    """Search bills with filters."""
    q = db.session.query(Bill).filter_by(user_id=user_id)

    if query:
        q = q.filter(Bill.name.ilike(f"%{query}%"))
    if amount_min is not None:
        q = q.filter(Bill.amount >= Decimal(str(amount_min)))
    if amount_max is not None:
        q = q.filter(Bill.amount <= Decimal(str(amount_max)))
    if date_from:
        q = q.filter(Bill.next_due_date >= date_from)
    if date_to:
        q = q.filter(Bill.next_due_date <= date_to)

    count = q.count()
    bills = q.all()

    results = []
    for b in bills:
        results.append({
            "id": b.id,
            "type": "bill",
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "category": None,
            "category_id": None,
            "date": b.next_due_date.isoformat() if b.next_due_date else None,
            "expense_type": "BILL",
            "cadence": b.cadence.value if b.cadence else None,
            "active": b.active,
            "autopay": b.autopay_enabled,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })

    return results, count


def _search_recurring(
    user_id, query, category_id, amount_min, amount_max,
    expense_type, sort_by, sort_order,
) -> tuple[list[dict], int]:
    """Search recurring expenses with filters."""
    q = db.session.query(RecurringExpense).filter_by(user_id=user_id)

    if query:
        q = q.filter(RecurringExpense.notes.ilike(f"%{query}%"))
    if category_id:
        q = q.filter(RecurringExpense.category_id == category_id)
    if amount_min is not None:
        q = q.filter(RecurringExpense.amount >= Decimal(str(amount_min)))
    if amount_max is not None:
        q = q.filter(RecurringExpense.amount <= Decimal(str(amount_max)))
    if expense_type:
        q = q.filter(RecurringExpense.expense_type == expense_type.upper())

    count = q.count()
    items = q.all()

    results = []
    for r in items:
        cat = db.session.get(Category, r.category_id) if r.category_id else None
        results.append({
            "id": r.id,
            "type": "recurring",
            "name": r.notes or "",
            "amount": float(r.amount),
            "currency": r.currency,
            "category": cat.name if cat else None,
            "category_id": r.category_id,
            "date": r.start_date.isoformat() if r.start_date else None,
            "expense_type": r.expense_type,
            "cadence": r.cadence.value if r.cadence else None,
            "active": r.active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return results, count


def _sort_results(results: list[dict], sort_by: str, sort_order: str) -> list[dict]:
    """Sort combined results from multiple entity types."""
    key_map = {
        "date": lambda x: x.get("date") or "",
        "amount": lambda x: x.get("amount", 0),
        "name": lambda x: (x.get("name") or "").lower(),
        "type": lambda x: x.get("type", ""),
    }
    key_fn = key_map.get(sort_by, key_map["date"])
    reverse = sort_order.lower() == "desc"
    return sorted(results, key=key_fn, reverse=reverse)
