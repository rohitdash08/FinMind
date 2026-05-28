"""Tests for Dashboard Service."""

import pytest


class TestDashboard:
    def test_empty_dashboard(self):
        from app.services.dashboard_service import DashboardService
        svc = DashboardService()
        result = svc.get_dashboard([], {})
        assert "overview" in result
        assert result["overview"]["total_income"] == 0

    def test_dashboard_with_data(self):
        from app.services.dashboard_service import DashboardService
        svc = DashboardService()
        txns = [
            {"amount": 5000, "category": "salary", "type": "income", "date": "2025-01-01"},
            {"amount": 1200, "category": "rent", "type": "expense", "date": "2025-01-05"},
            {"amount": 300, "category": "food", "type": "expense", "date": "2025-01-10"},
        ]
        budgets = {"rent": 1200, "food": 400}
        result = svc.get_dashboard(txns, budgets)
        assert result["overview"]["total_income"] == 5000
        assert result["overview"]["total_expenses"] == 1500
        assert len(result["budget_progress"]) == 2

    def test_quick_summary(self):
        from app.services.dashboard_service import DashboardService
        svc = DashboardService()
        result = svc.get_quick_summary([])
        assert "today" in result
        assert "this_week" in result
        assert "this_month" in result

    def test_alerts_budget_exceeded(self):
        from app.services.dashboard_service import DashboardService
        svc = DashboardService()
        txns = [
            {"amount": 1500, "category": "rent", "type": "expense",
             "date": "2025-05-10"},
        ]
        alerts = svc.get_alerts(txns, {"rent": 1200})
        assert any(a["type"] == "budget_exceeded" for a in alerts)
