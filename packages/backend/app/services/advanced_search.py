"""
Advanced Search Service for transactions and bills.

Supports filtering by:
- keyword: full-text match on description/notes
- category: category name (partial match)
- amount_min / amount_max: amount range
- date_from / date_to: date range (ISO format YYYY-MM-DD)
- tags: comma-separated tags (matches any)
- merchant: merchant/payee name (partial match)
- record_type: "expense", "bill", or "all" (default)

Returns paginated results with hit counts.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime

from ..models import Expense, Bill, Category
from sqlalchemy import or_, and_


@dataclass
class SearchResult:
    record_type: str
    record_id: int
    description: str
    amount: float
    date_str: str
    category: Optional[str]
    extra: dict = field(default_factory=dict)
    match_reason: str = ""


@dataclass
class AdvancedSearchResult:
    query: dict
    total_expenses: int
    total_bills: int
    total_hits: int
    page: int
    page_size: int
    results: list[SearchResult]
    searched_at: str


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _expense_to_result(exp, match_reason: str = "") -> SearchResult:
    cat_name = None
    if exp.category_id:
        cat = Category.query.get(exp.category_id)
        cat_name = cat.name if cat else None

    return SearchResult(
        record_type="expense",
        record_id=exp.id,
        description=exp.description or "",
        amount=float(exp.amount or 0),
        date_str=exp.date.isoformat() if exp.date else "",
        category=cat_name,
        match_reason=match_reason,
    )


def _bill_to_result(bill, match_reason: str = "") -> SearchResult:
    return SearchResult(
        record_type="bill",
        record_id=bill.id,
        description=getattr(bill, "name", "") or "",
        amount=float(getattr(bill, "amount", 0) or 0),
        date_str=bill.due_date.isoformat() if bill.due_date else "",
        category=None,
        match_reason=match_reason,
        extra={
            "status": getattr(bill, "status", ""),
            "frequency": getattr(bill, "frequency", ""),
        },
    )


def search_transactions(
    user_id: int,
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    merchant: Optional[str] = None,
    record_type: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> AdvancedSearchResult:
    """
    Search across expenses and bills with multi-field filters.

    Args:
        user_id: User ID
        keyword: Full-text match on description
        category: Category name filter (partial)
        amount_min: Minimum amount
        amount_max: Maximum amount
        date_from: Start date ISO string
        date_to: End date ISO string
        merchant: Merchant/payee match (partial)
        record_type: "expense", "bill", or "all"
        page: Page number (1-based)
        page_size: Results per page (max 100)

    Returns:
        AdvancedSearchResult with paginated results.
    """
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    date_from_obj = _parse_date(date_from)
    date_to_obj = _parse_date(date_to)

    expense_results: list[SearchResult] = []
    bill_results: list[SearchResult] = []

    # ── Expense search ──
    if record_type in ("expense", "all"):
        query = Expense.query.filter(Expense.user_id == user_id)

        if keyword:
            query = query.filter(Expense.description.ilike(f"%{keyword}%"))

        if merchant:
            query = query.filter(Expense.description.ilike(f"%{merchant}%"))

        if amount_min is not None:
            query = query.filter(Expense.amount >= amount_min)

        if amount_max is not None:
            query = query.filter(Expense.amount <= amount_max)

        if date_from_obj:
            query = query.filter(Expense.date >= date_from_obj)

        if date_to_obj:
            query = query.filter(Expense.date <= date_to_obj)

        if category:
            # Join through category
            cat_matches = Category.query.filter(
                Category.user_id == user_id,
                Category.name.ilike(f"%{category}%"),
            ).all()
            cat_ids = [c.id for c in cat_matches]
            if cat_ids:
                query = query.filter(Expense.category_id.in_(cat_ids))
            else:
                query = query.filter(False)  # No matching categories

        exps = query.order_by(Expense.date.desc()).all()
        for exp in exps:
            reasons = []
            if keyword and keyword.lower() in (exp.description or "").lower():
                reasons.append(f"description contains '{keyword}'")
            if merchant and merchant.lower() in (exp.description or "").lower():
                reasons.append(f"merchant matches '{merchant}'")
            expense_results.append(_expense_to_result(exp, ", ".join(reasons) if reasons else "filter match"))

    # ── Bill search ──
    if record_type in ("bill", "all"):
        q = Bill.query.filter(Bill.user_id == user_id)

        if keyword:
            q = q.filter(Bill.name.ilike(f"%{keyword}%"))

        if merchant:
            q = q.filter(Bill.name.ilike(f"%{merchant}%"))

        if amount_min is not None:
            q = q.filter(Bill.amount >= amount_min)

        if amount_max is not None:
            q = q.filter(Bill.amount <= amount_max)

        if date_from_obj:
            q = q.filter(Bill.due_date >= date_from_obj)

        if date_to_obj:
            q = q.filter(Bill.due_date <= date_to_obj)

        bills = q.order_by(Bill.due_date.desc()).all()
        for bill in bills:
            reasons = []
            if keyword and keyword.lower() in (getattr(bill, "name", "") or "").lower():
                reasons.append(f"name contains '{keyword}'")
            bill_results.append(_bill_to_result(bill, ", ".join(reasons) if reasons else "filter match"))

    # Combine and paginate
    all_results = expense_results + bill_results
    total_hits = len(all_results)
    paginated = all_results[offset:offset + page_size]

    return AdvancedSearchResult(
        query={
            "keyword": keyword,
            "category": category,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "date_from": date_from,
            "date_to": date_to,
            "merchant": merchant,
            "record_type": record_type,
        },
        total_expenses=len(expense_results),
        total_bills=len(bill_results),
        total_hits=total_hits,
        page=page,
        page_size=page_size,
        results=paginated,
        searched_at=datetime.utcnow().isoformat() + "Z",
    )