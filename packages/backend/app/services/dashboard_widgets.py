"""Customizable dashboard widgets & visibility (issue #103)."""
import json, logging
from ..extensions import redis_client

logger = logging.getLogger("finmind.widgets")
KEY = "dashboard:widgets:"
TTL = 60 * 60 * 24 * 365

DEFAULT_WIDGETS = [
    {"id": "net_flow", "label": "Net Flow", "visible": True, "position": 0},
    {"id": "monthly_summary", "label": "Monthly Summary", "visible": True, "position": 1},
    {"id": "category_breakdown", "label": "Category Breakdown", "visible": True, "position": 2},
    {"id": "upcoming_bills", "label": "Upcoming Bills", "visible": True, "position": 3},
    {"id": "recent_transactions", "label": "Recent Transactions", "visible": True, "position": 4},
    {"id": "savings_goals", "label": "Savings Goals", "visible": False, "position": 5},
    {"id": "spending_heatmap", "label": "Spending Heatmap", "visible": False, "position": 6},
    {"id": "weekly_digest", "label": "Weekly Digest", "visible": False, "position": 7},
]


def get_widgets(user_id: int) -> list:
    raw = redis_client.get(f"{KEY}{user_id}")
    return json.loads(raw) if raw else DEFAULT_WIDGETS[:]


def update_widget(user_id: int, widget_id: str, visible: bool = None, position: int = None) -> bool:
    widgets = get_widgets(user_id)
    for w in widgets:
        if w["id"] == widget_id:
            if visible is not None: w["visible"] = visible
            if position is not None: w["position"] = position
            redis_client.setex(f"{KEY}{user_id}", TTL, json.dumps(widgets))
            return True
    return False


def reorder_widgets(user_id: int, order: list[str]) -> list:
    """Reorder widgets by providing list of widget IDs in desired order."""
    widgets = {w["id"]: w for w in get_widgets(user_id)}
    result = []
    for i, wid in enumerate(order):
        if wid in widgets:
            widgets[wid]["position"] = i
            result.append(widgets[wid])
    # Append any not in order list
    positioned = {w["id"] for w in result}
    for w in widgets.values():
        if w["id"] not in positioned:
            result.append(w)
    redis_client.setex(f"{KEY}{user_id}", TTL, json.dumps(result))
    return result
