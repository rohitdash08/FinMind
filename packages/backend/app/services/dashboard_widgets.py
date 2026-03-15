"""Customizable dashboard widgets service.

Allows users to show/hide, reorder, and configure dashboard sections.
Provides default widget layouts and per-user customization.
"""

from datetime import datetime
from typing import Optional

from app.extensions import db
from app.models import DashboardWidget


# Default widgets available to all users
DEFAULT_WIDGETS = [
    {"widget_key": "spending_overview", "display_name": "Spending Overview", "position": 0},
    {"widget_key": "recent_transactions", "display_name": "Recent Transactions", "position": 1},
    {"widget_key": "budget_progress", "display_name": "Budget Progress", "position": 2},
    {"widget_key": "upcoming_bills", "display_name": "Upcoming Bills", "position": 3},
    {"widget_key": "category_breakdown", "display_name": "Category Breakdown", "position": 4},
    {"widget_key": "savings_goals", "display_name": "Savings Goals", "position": 5},
    {"widget_key": "recurring_expenses", "display_name": "Recurring Expenses", "position": 6},
    {"widget_key": "financial_health", "display_name": "Financial Health Score", "position": 7},
]


# ── Widget Layout ─────────────────────────────────────────────────


def get_layout(user_id: int) -> list:
    """Get the dashboard layout for a user.

    Returns user's custom layout or defaults if none configured.
    """
    widgets = (
        DashboardWidget.query
        .filter_by(user_id=user_id)
        .order_by(DashboardWidget.position)
        .all()
    )

    if not widgets:
        return [
            {**w, "visible": True, "config": {}}
            for w in DEFAULT_WIDGETS
        ]

    return [_serialize_widget(w) for w in widgets]


def initialize_layout(user_id: int) -> list:
    """Initialize default widget layout for a user.

    Creates widget records from defaults. Idempotent — skips
    if layout already exists.
    """
    existing = DashboardWidget.query.filter_by(user_id=user_id).count()
    if existing > 0:
        return get_layout(user_id)

    for w in DEFAULT_WIDGETS:
        widget = DashboardWidget(
            user_id=user_id,
            widget_key=w["widget_key"],
            display_name=w["display_name"],
            position=w["position"],
            visible=True,
        )
        db.session.add(widget)

    db.session.commit()
    return get_layout(user_id)


def reset_layout(user_id: int) -> list:
    """Reset layout to defaults by deleting all custom widgets."""
    DashboardWidget.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    return initialize_layout(user_id)


# ── Widget Visibility ─────────────────────────────────────────────


def toggle_visibility(user_id: int, widget_key: str, visible: bool) -> dict:
    """Show or hide a dashboard widget."""
    widget = _get_or_create(user_id, widget_key)
    if not widget:
        return {"error": f"Unknown widget: {widget_key}"}

    widget.visible = visible
    widget.updated_at = datetime.utcnow()
    db.session.commit()
    return _serialize_widget(widget)


def bulk_update_visibility(user_id: int, updates: dict) -> list:
    """Update visibility for multiple widgets at once.

    Args:
        updates: dict of {widget_key: visible_bool}
    """
    _ensure_layout(user_id)
    for key, visible in updates.items():
        widget = DashboardWidget.query.filter_by(
            user_id=user_id, widget_key=key
        ).first()
        if widget:
            widget.visible = visible
            widget.updated_at = datetime.utcnow()

    db.session.commit()
    return get_layout(user_id)


# ── Widget Reordering ─────────────────────────────────────────────


def reorder_widgets(user_id: int, order: list) -> list:
    """Reorder dashboard widgets.

    Args:
        order: list of widget_keys in desired order
    """
    _ensure_layout(user_id)
    for position, key in enumerate(order):
        widget = DashboardWidget.query.filter_by(
            user_id=user_id, widget_key=key
        ).first()
        if widget:
            widget.position = position
            widget.updated_at = datetime.utcnow()

    db.session.commit()
    return get_layout(user_id)


# ── Widget Configuration ──────────────────────────────────────────


def update_widget_config(user_id: int, widget_key: str, config: dict) -> dict:
    """Update widget-specific configuration."""
    widget = _get_or_create(user_id, widget_key)
    if not widget:
        return {"error": f"Unknown widget: {widget_key}"}

    widget.config = config
    widget.updated_at = datetime.utcnow()
    db.session.commit()
    return _serialize_widget(widget)


def get_widget(user_id: int, widget_key: str) -> dict:
    """Get a single widget's details."""
    widget = DashboardWidget.query.filter_by(
        user_id=user_id, widget_key=widget_key
    ).first()
    if not widget:
        # Check if it's a known default
        default = next((w for w in DEFAULT_WIDGETS if w["widget_key"] == widget_key), None)
        if default:
            return {**default, "visible": True, "config": {}}
        return {"error": f"Unknown widget: {widget_key}"}
    return _serialize_widget(widget)


# ── Available Widgets ─────────────────────────────────────────────


def get_available_widgets() -> list:
    """List all available widget types."""
    return [
        {"widget_key": w["widget_key"], "display_name": w["display_name"]}
        for w in DEFAULT_WIDGETS
    ]


# ── Helpers ───────────────────────────────────────────────────────


def _ensure_layout(user_id: int):
    """Ensure user has a layout initialized."""
    if DashboardWidget.query.filter_by(user_id=user_id).count() == 0:
        initialize_layout(user_id)


def _get_or_create(user_id: int, widget_key: str) -> Optional[DashboardWidget]:
    """Get a widget or create it from defaults."""
    _ensure_layout(user_id)
    widget = DashboardWidget.query.filter_by(
        user_id=user_id, widget_key=widget_key
    ).first()
    return widget


def _serialize_widget(w: DashboardWidget) -> dict:
    return {
        "id": w.id,
        "widget_key": w.widget_key,
        "display_name": w.display_name,
        "visible": w.visible,
        "position": w.position,
        "config": w.config or {},
    }
