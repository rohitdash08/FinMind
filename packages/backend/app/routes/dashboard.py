import json
from datetime import date
from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Bill, Expense, Category, DashboardPreference
from ..services.cache import cache_get, cache_set, dashboard_summary_key

bp = Blueprint("dashboard", __name__)

# ---------------------------------------------------------------------------
# Widget defaults — the canonical ordered list of dashboard widgets.
# The frontend uses the same IDs to look up its render map.
# ---------------------------------------------------------------------------
DEFAULT_WIDGETS = [
    {"id": "summary_cards", "label": "Summary Cards", "visible": True},
    {"id": "recent_transactions", "label": "Recent Transactions", "visible": True},
    {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": True},
    {"id": "category_breakdown", "label": "Category Breakdown", "visible": True},
]

_VALID_WIDGET_IDS = {w["id"] for w in DEFAULT_WIDGETS}


def _default_widgets():
    return [dict(w) for w in DEFAULT_WIDGETS]


@bp.get("/summary")
@jwt_required()
def dashboard_summary():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400
    key = dashboard_summary_key(uid, ym)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    payload = {
        "period": {"month": ym},
        "summary": {
            "net_flow": 0.0,
            "monthly_income": 0.0,
            "monthly_expenses": 0.0,
            "upcoming_bills_total": 0.0,
            "upcoming_bills_count": 0,
        },
        "recent_transactions": [],
        "upcoming_bills": [],
        "category_breakdown": [],
        "errors": [],
    }

    year, month = map(int, ym.split("-"))
    today = date.today()

    try:
        income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        expenses = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        payload["summary"]["monthly_income"] = float(income or 0)
        payload["summary"]["monthly_expenses"] = float(expenses or 0)
        payload["summary"]["net_flow"] = round(
            payload["summary"]["monthly_income"]
            - payload["summary"]["monthly_expenses"],
            2,
        )
    except Exception:
        payload["errors"].append("summary_unavailable")

    try:
        rows = (
            db.session.query(Expense)
            .filter(Expense.user_id == uid)
            .order_by(Expense.spent_at.desc(), Expense.id.desc())
            .limit(10)
            .all()
        )
        payload["recent_transactions"] = [
            {
                "id": e.id,
                "description": e.notes or "Transaction",
                "amount": float(e.amount),
                "date": e.spent_at.isoformat(),
                "type": e.expense_type,
                "category_id": e.category_id,
                "currency": e.currency,
            }
            for e in rows
        ]
    except Exception:
        payload["errors"].append("recent_transactions_unavailable")

    try:
        bills = (
            db.session.query(Bill)
            .filter(
                Bill.user_id == uid,
                Bill.active.is_(True),
                Bill.next_due_date >= today,
            )
            .order_by(Bill.next_due_date.asc())
            .limit(8)
            .all()
        )
        payload["upcoming_bills"] = [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value,
                "channel_email": b.channel_email,
                "channel_whatsapp": b.channel_whatsapp,
            }
            for b in bills
        ]
        payload["summary"]["upcoming_bills_total"] = round(
            sum(float(b.amount) for b in bills), 2
        )
        payload["summary"]["upcoming_bills_count"] = len(bills)
    except Exception:
        payload["errors"].append("upcoming_bills_unavailable")

    try:
        category_rows = (
            db.session.query(
                Expense.category_id,
                func.coalesce(Category.name, "Uncategorized").label("category_name"),
                func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
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
        total = sum(float(r.total_amount or 0) for r in category_rows)
        payload["category_breakdown"] = [
            {
                "category_id": r.category_id,
                "category_name": r.category_name,
                "amount": float(r.total_amount or 0),
                "share_pct": (
                    round((float(r.total_amount or 0) / total) * 100, 2)
                    if total > 0
                    else 0
                ),
            }
            for r in category_rows
        ]
    except Exception:
        payload["errors"].append("category_breakdown_unavailable")

    cache_set(key, payload, ttl_seconds=300)
    return jsonify(payload)


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    year, month = ym.split("-")
    if not (year.isdigit() and month.isdigit()):
        return False
    m = int(month)
    return 1 <= m <= 12


# ---------------------------------------------------------------------------
# Dashboard preferences: GET /dashboard/preferences
#                        PUT /dashboard/preferences
# ---------------------------------------------------------------------------


@bp.get("/preferences")
@jwt_required()
def get_preferences():
    """Return the user's saved dashboard widget config, or the default."""
    uid = int(get_jwt_identity())
    pref = DashboardPreference.query.filter_by(user_id=uid).first()
    if pref is None:
        return jsonify({"widgets": _default_widgets()})
    try:
        widgets = json.loads(pref.widgets)
    except (json.JSONDecodeError, TypeError):
        widgets = _default_widgets()
    return jsonify({"widgets": widgets})


@bp.put("/preferences")
@jwt_required()
def update_preferences():
    """Save the user's dashboard widget config.

    Expected body::

        {
          "widgets": [
            {"id": "summary_cards",        "label": "Summary Cards",        "visible": true},
            {"id": "recent_transactions",  "label": "Recent Transactions",  "visible": false},
            ...
          ]
        }

    Rules:
    - ``widgets`` must be a list.
    - Each item must have ``id`` (string, one of the known widget IDs),
      ``label`` (string) and ``visible`` (bool).
    - Unknown extra fields are preserved (forward-compatible).
    - Unknown ``id`` values are rejected with 422.
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    widgets = body.get("widgets")

    if not isinstance(widgets, list):
        return jsonify(error="'widgets' must be a list"), 422

    validated = []
    seen_ids = set()
    for item in widgets:
        if not isinstance(item, dict):
            return jsonify(error="Each widget must be an object"), 422
        w_id = item.get("id")
        if not isinstance(w_id, str) or w_id not in _VALID_WIDGET_IDS:
            return (
                jsonify(
                    error=f"Unknown widget id '{w_id}'. "
                    f"Valid ids: {sorted(_VALID_WIDGET_IDS)}"
                ),
                422,
            )
        if w_id in seen_ids:
            return jsonify(error=f"Duplicate widget id '{w_id}'"), 422
        seen_ids.add(w_id)
        if not isinstance(item.get("label"), str):
            return jsonify(error=f"Widget '{w_id}' must have a string label"), 422
        if not isinstance(item.get("visible"), bool):
            return jsonify(error=f"Widget '{w_id}' 'visible' must be a boolean"), 422
        validated.append(
            {"id": w_id, "label": item["label"], "visible": item["visible"]}
        )

    pref = DashboardPreference.query.filter_by(user_id=uid).first()
    if pref is None:
        pref = DashboardPreference(user_id=uid, widgets=json.dumps(validated))
        db.session.add(pref)
    else:
        pref.widgets = json.dumps(validated)
    db.session.commit()
    return jsonify({"widgets": validated}), 200
