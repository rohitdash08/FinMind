"""Tests for dashboard widgets (issue #103)."""
import json
from unittest.mock import MagicMock, patch

def _mock_redis():
    store = {}
    r = MagicMock()
    def get(k): v=store.get(k); return v.encode() if isinstance(v,str) else v
    def setex(k,t,v): store[k]=v
    r.get.side_effect=get; r.setex.side_effect=setex
    return r, store

def test_default_widgets():
    r,_ = _mock_redis()
    with patch("app.services.dashboard_widgets.redis_client", r):
        from app.services.dashboard_widgets import get_widgets, DEFAULT_WIDGETS
        widgets = get_widgets(1)
        assert len(widgets) == len(DEFAULT_WIDGETS)
        assert widgets[0]["id"] == "net_flow"

def test_toggle_visibility():
    r,_ = _mock_redis()
    with patch("app.services.dashboard_widgets.redis_client", r):
        from app.services.dashboard_widgets import update_widget, get_widgets
        update_widget(1, "savings_goals", visible=True)
        widgets = get_widgets(1)
        sg = next(w for w in widgets if w["id"] == "savings_goals")
        assert sg["visible"] is True

def test_reorder_widgets():
    r,_ = _mock_redis()
    with patch("app.services.dashboard_widgets.redis_client", r):
        from app.services.dashboard_widgets import reorder_widgets
        result = reorder_widgets(1, ["upcoming_bills", "net_flow"])
        assert result[0]["id"] == "upcoming_bills"
        assert result[1]["id"] == "net_flow"

def test_update_unknown_widget():
    r,_ = _mock_redis()
    with patch("app.services.dashboard_widgets.redis_client", r):
        from app.services.dashboard_widgets import update_widget
        assert update_widget(1, "nonexistent_widget") is False
