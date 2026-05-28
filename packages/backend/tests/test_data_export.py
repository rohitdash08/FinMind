"""Tests for data export service."""

import pytest


class TestCSVExport:
    def test_basic_csv(self):
        from app.services.data_export import export_csv
        txs = [{"date": "2025-06-01", "merchant": "Starbucks", "category": "food", "amount": 5.0}]
        csv = export_csv(txs)
        assert "Starbucks" in csv
        assert "Date" in csv

    def test_csv_with_filters(self):
        from app.services.data_export import export_csv
        txs = [
            {"date": "2025-06-01", "merchant": "A", "amount": 10},
            {"date": "2025-05-01", "merchant": "B", "amount": 20},
        ]
        csv = export_csv(txs, {"start_date": "2025-06-01"})
        assert "A" in csv
        assert "B" not in csv


class TestJSONExport:
    def test_basic_json(self):
        from app.services.data_export import export_json
        txs = [{"date": "2025-06-01", "merchant": "A", "category": "food", "amount": 50}]
        result = export_json(txs)
        assert result["total_transactions"] == 1
        assert result["total_amount"] == 50.0

    def test_category_summary(self):
        from app.services.data_export import export_json
        txs = [
            {"category": "food", "amount": 30},
            {"category": "food", "amount": 20},
            {"category": "transport", "amount": 10},
        ]
        result = export_json(txs)
        assert result["categories_summary"]["food"] == 50.0


class TestOFXExport:
    def test_basic_ofx(self):
        from app.services.data_export import export_ofx
        txs = [{"date": "2025-06-01", "merchant": "Test", "amount": -50, "category": "food"}]
        ofx = export_ofx(txs)
        assert "<OFX>" in ofx
        assert "DEBIT" in ofx

    def test_credit_transaction(self):
        from app.services.data_export import export_ofx
        txs = [{"date": "2025-06-01", "merchant": "Refund", "amount": 50}]
        ofx = export_ofx(txs)
        assert "CREDIT" in ofx


class TestSummaryReport:
    def test_basic_summary(self):
        from app.services.data_export import generate_summary_report
        txs = [{"category": "food", "amount": 100}, {"category": "rent", "amount": 500}]
        result = generate_summary_report(txs)
        assert result["total_spending"] == 600.0
        assert result["top_category"] == "rent"
