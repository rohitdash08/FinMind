"""Tests for Report Generator."""

import pytest


class TestReportGenerator:
    def test_add_transaction_and_report(self):
        from app.services.report_generator import ReportGeneratorService
        svc = ReportGeneratorService()
        svc.add_transaction("u1", 5000, "salary", "2025-01-01", "income")
        svc.add_transaction("u1", 1200, "rent", "2025-01-05", "expense")
        svc.add_transaction("u1", 300, "food", "2025-01-10", "expense")
        report = svc.generate_report("u1", "income_expense", start_date="2025-01-01", end_date="2025-01-31")
        assert report["data"]["total_income"] == 5000
        assert report["data"]["total_expense"] == 1500

    def test_category_report(self):
        from app.services.report_generator import ReportGeneratorService
        svc = ReportGeneratorService()
        svc.add_transaction("u1", 500, "rent", "2025-01-01", "expense")
        svc.add_transaction("u1", 200, "food", "2025-01-02", "expense")
        report = svc.generate_report("u1", "category", start_date="2025-01-01", end_date="2025-01-31")
        assert len(report["data"]["categories"]) == 2

    def test_savings_report(self):
        from app.services.report_generator import ReportGeneratorService
        svc = ReportGeneratorService()
        svc.add_transaction("u1", 5000, "salary", "2025-01-01", "income")
        svc.add_transaction("u1", 3000, "expenses", "2025-01-15", "expense")
        report = svc.generate_report("u1", "savings", start_date="2025-01-01", end_date="2025-01-31")
        assert report["data"]["savings_rate"] == 40.0
        assert report["data"]["savings_health"] == "excellent"

    def test_budget_vs_actual(self):
        from app.services.report_generator import ReportGeneratorService
        svc = ReportGeneratorService()
        svc.set_budget("u1", "rent", 1200)
        svc.set_budget("u1", "food", 500)
        svc.add_transaction("u1", 1300, "rent", "2025-01-05", "expense")
        svc.add_transaction("u1", 400, "food", "2025-01-10", "expense")
        report = svc.generate_report("u1", "budget_vs_actual", start_date="2025-01-01", end_date="2025-01-31")
        assert any(c["status"] == "over" for c in report["data"]["categories"])
