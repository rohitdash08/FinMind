"""Customizable dashboard widgets & visibility.

Users can configure which widgets appear on their dashboard,
reorder them, resize, and toggle visibility.
"""

from datetime import datetime
from ..extensions import db


class DashboardWidget(db.Model):
    __tablename__ = "dashboard_widgets"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    widget_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    position = db.Column(db.Integer, default=0)
    width = db.Column(db.String(20), default="half")  # full, half, third
    visible = db.Column(db.Boolean, default=True)
    config = db.Column(db.Text, default="{}")  # JSON config
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Available widget types
WIDGET_CATALOG = [
    {"type": "spending_summary", "title": "Spending Summary", "description": "Total spending overview"},
    {"type": "category_breakdown", "title": "Category Breakdown", "description": "Spending by category pie chart"},
    {"type": "recent_transactions", "title": "Recent Transactions", "description": "Latest transactions list"},
    {"type": "budget_progress", "title": "Budget Progress", "description": "Budget utilization bars"},
    {"type": "bills_upcoming", "title": "Upcoming Bills", "description": "Bills due soon"},
    {"type": "savings_goals", "title": "Savings Goals", "description": "Goal progress tracker"},
    {"type": "spending_trend", "title": "Spending Trend", "description": "Daily/weekly spending chart"},
    {"type": "income_vs_expense", "title": "Income vs Expense", "description": "Income and expense comparison"},
    {"type": "alerts", "title": "Alerts", "description": "Recent alerts and notifications"},
    {"type": "quick_add", "title": "Quick Add", "description": "Quick expense entry form"},
]


def get_catalog() -> list[dict]:
    return WIDGET_CATALOG


def get_widgets(user_id: int) -> list[dict]:
    widgets = (DashboardWidget.query.filter_by(user_id=user_id)
               .order_by(DashboardWidget.position).all())
    if not widgets:
        return _create_defaults(user_id)
    return [_serialize(w) for w in widgets]


def add_widget(user_id: int, widget_type: str, title: str | None = None,
               width: str = "half", config: str = "") -> dict:
    valid_types = [w["type"] for w in WIDGET_CATALOG]
    if widget_type not in valid_types:
        raise ValueError(f"Unknown widget type: {widget_type}")
    if width not in ("full", "half", "third"):
        raise ValueError("Width must be full, half, or third")

    max_pos = db.session.query(db.func.max(DashboardWidget.position)).filter_by(user_id=user_id).scalar() or 0

    catalog_entry = next(w for w in WIDGET_CATALOG if w["type"] == widget_type)
    w = DashboardWidget(
        user_id=user_id, widget_type=widget_type,
        title=title or catalog_entry["title"],
        position=max_pos + 1, width=width, config=config,
    )
    db.session.add(w)
    db.session.commit()
    return _serialize(w)


def update_widget(user_id: int, widget_id: int, **kwargs) -> dict | None:
    w = DashboardWidget.query.filter_by(id=widget_id, user_id=user_id).first()
    if not w:
        return None
    for key in ("title", "width", "visible", "config", "position"):
        if key in kwargs and kwargs[key] is not None:
            setattr(w, key, kwargs[key])
    db.session.commit()
    return _serialize(w)


def delete_widget(user_id: int, widget_id: int) -> bool:
    w = DashboardWidget.query.filter_by(id=widget_id, user_id=user_id).first()
    if not w:
        return False
    db.session.delete(w)
    db.session.commit()
    return True


def reorder_widgets(user_id: int, widget_ids: list[int]) -> list[dict]:
    widgets = DashboardWidget.query.filter_by(user_id=user_id).all()
    id_map = {w.id: w for w in widgets}
    for pos, wid in enumerate(widget_ids):
        if wid in id_map:
            id_map[wid].position = pos
    db.session.commit()
    return get_widgets(user_id)


def _create_defaults(user_id: int) -> list[dict]:
    defaults = ["spending_summary", "category_breakdown", "recent_transactions",
                "budget_progress", "bills_upcoming"]
    result = []
    for i, wtype in enumerate(defaults):
        entry = next(w for w in WIDGET_CATALOG if w["type"] == wtype)
        w = DashboardWidget(
            user_id=user_id, widget_type=wtype,
            title=entry["title"], position=i,
            width="full" if i == 0 else "half",
        )
        db.session.add(w)
        result.append(w)
    db.session.commit()
    return [_serialize(w) for w in result]


def _serialize(w: DashboardWidget) -> dict:
    return {
        "id": w.id, "widget_type": w.widget_type, "title": w.title,
        "position": w.position, "width": w.width, "visible": w.visible,
        "config": w.config,
    }
