"""Tests for Receipt Scanner."""

import pytest


class TestReceiptScanner:
    def test_scan_text(self):
        from app.services.receipt_scanner import ReceiptScannerService
        svc = ReceiptScannerService()
        text = "Walmart\n2025-01-15\nMilk $3.99\nBread $2.49\nTotal: $6.48\nTax: $0.52"
        result = svc.scan_text("user1", text)
        assert result["status"] == "scanned"
        assert result["store"] == "Walmart"
        assert result["total"] == 6.48

    def test_duplicate_detection(self):
        from app.services.receipt_scanner import ReceiptScannerService
        svc = ReceiptScannerService()
        text = "Target\nTotal: $25.99\n2025-01-15"
        svc.scan_text("user1", text)
        result = svc.scan_text("user1", text)
        assert result["status"] == "duplicate"

    def test_upload_receipt(self):
        from app.services.receipt_scanner import ReceiptScannerService
        svc = ReceiptScannerService()
        result = svc.upload_receipt("user1", "Starbucks", 5.75, "2025-01-15",
                                     category="dining")
        assert result["status"] == "uploaded"
        assert result["store"] == "Starbucks"

    def test_search(self):
        from app.services.receipt_scanner import ReceiptScannerService
        svc = ReceiptScannerService()
        svc.upload_receipt("user1", "Walmart", 50.0, "2025-01-10", category="groceries")
        svc.upload_receipt("user1", "Starbucks", 5.75, "2025-01-15", category="dining")
        results = svc.search("user1", store="Walmart")
        assert len(results) == 1

    def test_summary(self):
        from app.services.receipt_scanner import ReceiptScannerService
        svc = ReceiptScannerService()
        svc.upload_receipt("user1", "Walmart", 50.0, "2025-01-10", category="groceries")
        svc.upload_receipt("user1", "Target", 30.0, "2025-01-12", category="groceries")
        summary = svc.get_summary("user1")
        assert summary["total_receipts"] == 2
        assert summary["total_spent"] == 80.0

    def test_auto_categorize(self):
        from app.services.receipt_scanner import ReceiptScannerService
        svc = ReceiptScannerService()
        result = svc.scan_text("user1", "Starbucks\nCoffee latte $5.75\nTotal: $5.75\n2025-01-15")
        assert result["category"] == "dining"

    def test_export_csv(self):
        from app.services.receipt_scanner import ReceiptScannerService
        svc = ReceiptScannerService()
        svc.upload_receipt("user1", "Walmart", 50.0, "2025-01-10")
        exported = svc.export_data("user1", "csv")
        assert exported["format"] == "csv"
        assert "Walmart" in exported["data"]
