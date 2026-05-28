"""
Tests for financial health score calculation.
"""

import pytest
from app.services.health_score import (
    calculate_health_score,
    _calc_savings_strength,
    _calc_spending_stability,
    _calc_bill_reliability,
)


class TestSavingsStrength:
    def test_good_savings(self, app, db_session):
        with app.app_context():
            dim = _calc_savings_strength(5000, [
                {"amount": 1000}, {"amount": 1000}, {"amount": 1000}
            ])
            assert dim.score > 60
            assert dim.details["savings_rate"] > 0

    def test_no_income(self, app, db_session):
        with app.app_context():
            dim = _calc_savings_strength(0, [{"amount": 500}])
            assert dim.score < 30


class TestSpendingStability:
    def test_stable(self, app, db_session):
        with app.app_context():
            expenses = [
                {"amount": 500, "date": "2026-01-15"},
                {"amount": 520, "date": "2026-02-15"},
                {"amount": 490, "date": "2026-03-15"},
            ]
            dim = _calc_spending_stability(expenses)
            assert dim.score > 70

    def test_volatile(self, app, db_session):
        with app.app_context():
            expenses = [
                {"amount": 200, "date": "2026-01-15"},
                {"amount": 2000, "date": "2026-02-15"},
                {"amount": 100, "date": "2026-03-15"},
            ]
            dim = _calc_spending_stability(expenses)
            assert dim.score < 50


class TestBillReliability:
    def test_perfect(self, app, db_session):
        with app.app_context():
            bills = [
                {"status": "paid"}, {"status": "paid"}, {"status": "paid"}
            ]
            dim = _calc_bill_reliability(bills)
            assert dim.score >= 75

    def test_missed(self, app, db_session):
        with app.app_context():
            bills = [
                {"status": "paid"}, {"status": "missed"}, {"status": "overdue"}
            ]
            dim = _calc_bill_reliability(bills)
            assert dim.score < 70


class TestCompositeScore:
    def test_healthy(self, app, db_session):
        with app.app_context():
            report = calculate_health_score(
                income=5000,
                expenses=[{"amount": 300, "date": "2026-01-01"}] * 5,
                previous_expenses=[{"amount": 350, "date": "2025-12-01"}] * 5,
                bills=[{"status": "paid"}, {"status": "paid"}],
            )
            assert report.composite_score > 40
            assert report.grade in ["A+", "A", "B", "C", "D", "F"]
            assert len(report.dimensions) == 4
            assert report.trend in ["improving", "stable", "declining"]

    def test_unhealthy(self, app, db_session):
        with app.app_context():
            report = calculate_health_score(
                income=2000,
                expenses=[{"amount": 500, "date": "2026-01-01"}] * 8,
                bills=[{"status": "missed"}, {"status": "overdue"}],
            )
            assert report.composite_score < 60
