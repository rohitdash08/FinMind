"""Tests for Emergency Fund Calculator."""

import pytest


class TestEmergencyFund:
    def test_recommended(self):
        from app.services.emergency_fund import EmergencyFundService
        svc = EmergencyFundService()
        result = svc.calculate_recommended(3000, 5000, dependents=1)
        assert result["recommended_fund"] > 0
        assert result["recommended_months"] > 3

    def test_progress(self):
        from app.services.emergency_fund import EmergencyFundService
        svc = EmergencyFundService()
        result = svc.track_progress(10000, 3000, 5000)
        assert result["progress_percent"] > 0

    def test_savings_plan(self):
        from app.services.emergency_fund import EmergencyFundService
        svc = EmergencyFundService()
        result = svc.savings_plan(18000, 5000, 12, 5000, 3000)
        assert result["monthly_needed"] > 0

    def test_scenario(self):
        from app.services.emergency_fund import EmergencyFundService
        svc = EmergencyFundService()
        result = svc.scenario_analysis(3000, 15000, "job_loss")
        assert result["months_covered"] > 0
