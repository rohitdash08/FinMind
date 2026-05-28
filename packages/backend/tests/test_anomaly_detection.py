"""Tests for Anomaly Detection Engine."""

import pytest


class TestAnomalyDetection:
    def _make_txs(self, amounts, category="food"):
        txs = []
        for i, amt in enumerate(amounts):
            txs.append({"id": str(i), "amount": amt, "category": category,
                       "date": f"2024-01-{i+1:02d}T12:00:00", "merchant": "store"})
        return txs

    def test_amount_outlier_zscore(self):
        from app.services.anomaly_detection import AnomalyDetectionService
        svc = AnomalyDetectionService(z_threshold=2.0)
        amounts = [10, 15, 12, 11, 14, 500, 13, 10]
        txs = self._make_txs(amounts)
        results = svc.detect_amount_outliers(txs)
        assert len(results) > 0
        assert any(500 == abs(float(r.transaction["amount"])) for r in results)

    def test_no_outliers(self):
        from app.services.anomaly_detection import AnomalyDetectionService
        svc = AnomalyDetectionService()
        amounts = [10, 11, 10, 12, 11, 10]
        txs = self._make_txs(amounts)
        results = svc.detect_amount_outliers(txs)
        assert len(results) == 0

    def test_iqr_outlier(self):
        from app.services.anomaly_detection import AnomalyDetectionService
        svc = AnomalyDetectionService(iqr_multiplier=1.5)
        amounts = [10, 12, 11, 13, 10, 100]
        txs = self._make_txs(amounts)
        results = svc.detect_iqr_outliers(txs)
        assert len(results) > 0

    def test_full_analysis(self):
        from app.services.anomaly_detection import AnomalyDetectionService
        svc = AnomalyDetectionService()
        amounts = [10, 15, 12, 500, 13, 11]
        txs = self._make_txs(amounts)
        result = svc.full_analysis(txs)
        assert result["total_anomalies"] > 0
        assert "by_severity" in result

    def test_duplicate_detection(self):
        from app.services.anomaly_detection import AnomalyDetectionService
        svc = AnomalyDetectionService()
        txs = [
            {"id": "1", "amount": 50, "merchant": "amazon", "date": "2024-01-01T12:00:00"},
            {"id": "2", "amount": 50, "merchant": "amazon", "date": "2024-01-01T12:02:00"},
        ]
        results = svc.detect_duplicates(txs)
        assert len(results) > 0

    def test_category_deviation(self):
        from app.services.anomaly_detection import AnomalyDetectionService
        svc = AnomalyDetectionService()
        amounts = [10, 12, 11, 10, 13, 500]  # last one is way off
        txs = self._make_txs(amounts, category="groceries")
        results = svc.detect_category_deviation(txs)
        assert len(results) > 0
