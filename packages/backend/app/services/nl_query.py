"""Natural language finance query parser (issue #74)."""
import logging, re
from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.nl")

MONTH_NAMES = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    "january":1,"february":2,"march":3,"april":4,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
}


def _parse_month(text: str):
    today = date.today()
    t = text.lower()
    if "last month" in t:
        d = today - relativedelta(months=1); return d.year, d.month
    if "this month" in t or "current month" in t:
        return today.year, today.month
    for name, num in MONTH_NAMES.items():
        if name in t:
            year_match = re.search(r'\b(20\d{2})\b', t)
            year = int(year_match.group(1)) if year_match else today.year
            return year, num
    return today.year, today.month


def _parse_category(text: str, user_id: int):
    cats = db.session.query(Category).filter_by(user_id=user_id).all()
    t = text.lower()
    for cat in cats:
        if cat.name.lower() in t: return cat
    # Keyword fallback
    keywords = {"food":"Groceries","dining":"Dining","transport":"Transport",
                "shopping":"Shopping","bills":"Utilities","entertainment":"Entertainment"}
    for kw, cat_name in keywords.items():
        if kw in t: return type("Cat", (), {"id": None, "name": cat_name})()
    return None


def query(user_id: int, text: str) -> dict:
    """Parse natural language questions about finances."""
    t = text.lower().strip()
    year, month = _parse_month(t)

    # "how much did I spend on X"
    if re.search(r"(spend|spent|spending|cost|paid)", t):
        cat = _parse_category(t, user_id)
        q = db.session.query(func.coalesce(func.sum(Expense.amount), 0))\
                      .filter(Expense.user_id == user_id,
                              extract("year", Expense.spent_at) == year,
                              extract("month", Expense.spent_at) == month,
                              Expense.expense_type != "INCOME")
        if cat and cat.id: q = q.filter(Expense.category_id == cat.id)
        total = float(q.scalar() or 0)
        cat_label = cat.name if cat else "total"
        return {"answer": f"You spent ${total:.2f} on {cat_label} in {year}-{month:02d}.",
                "value": total, "period": f"{year}-{month:02d}", "category": cat_label}

    # "what is my income"
    if re.search(r"(income|earn|earned|salary|made)", t):
        total = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                      .filter(Expense.user_id == user_id,
                              extract("year", Expense.spent_at) == year,
                              extract("month", Expense.spent_at) == month,
                              Expense.expense_type == "INCOME").scalar() or 0)
        return {"answer": f"Your income in {year}-{month:02d} was ${total:.2f}.",
                "value": total, "period": f"{year}-{month:02d}"}

    # "how many transactions"
    if re.search(r"(how many|count|number of)\s*(transactions?|expenses?|purchases?)", t):
        count = db.session.query(func.count(Expense.id))\
                          .filter(Expense.user_id == user_id,
                                  extract("year", Expense.spent_at) == year,
                                  extract("month", Expense.spent_at) == month).scalar() or 0
        return {"answer": f"You had {count} transactions in {year}-{month:02d}.",
                "value": count, "period": f"{year}-{month:02d}"}

    return {"answer": "I couldn't understand that query. Try: 'How much did I spend on food last month?'",
            "value": None, "period": None}
