"""Tests for merchant heatmap and patterns."""

import pytest
from datetime import datetime, timezone, timedelta


class TestMerchantHeatmap:
    """Test merchant frequency heatmap generation."""

    def _make_transactions(self, merchants_days):
        """Helper: merchants_days = [(merchant, amount, day_offset, hour)]"""
        txs = []
        for merchant, amount, day_offset, hour in merchants_days:
            dt = datetime(2025, 6, 2, hour, 0, tzinfo=timezone.utc) + timedelta(days=day_offset)
            txs.append({
                "merchant": merchant,
                "amount": amount,
                "date": dt.isoformat(),
            })
        return txs

    def test_basic_heatmap_day_of_week(self):
        from app.services.merchant_heatmap import generate_merchant_heatmap

        txs = self._make_transactions([
            ("Starbucks", 5.0, 0, 8),   # Monday
            ("Starbucks", 5.0, 1, 8),   # Tuesday
            ("Amazon", 50.0, 5, 14),    # Saturday
        ])

        result = generate_merchant_heatmap(txs, group_by="day_of_week", top_n=5)
        assert "heatmap" in result
        assert len(result["merchants"]) == 2
        assert "Monday" in result["time_slots"]

    def test_heatmap_hour_of_day(self):
        from app.services.merchant_heatmap import generate_merchant_heatmap

        txs = self._make_transactions([
            ("Starbucks", 5.0, 0, 8),
            ("Starbucks", 5.0, 0, 8),
            ("Starbucks", 5.0, 0, 9),
        ])

        result = generate_merchant_heatmap(txs, group_by="hour_of_day")
        assert len(result["time_slots"]) == 24
        # Starbucks at hour 8 should have count 2
        starbucks_row = next(r for r in result["heatmap"] if r["merchant"] == "Starbucks")
        assert starbucks_row["8"]["transaction_count"] == 2

    def test_top_n_merchants(self):
        from app.services.merchant_heatmap import generate_merchant_heatmap

        txs = self._make_transactions([
            (f"Shop{i}", 10.0 * i, 0, 10) for i in range(1, 15)
        ])

        result = generate_merchant_heatmap(txs, top_n=5)
        assert len(result["merchants"]) == 5

    def test_empty_transactions(self):
        from app.services.merchant_heatmap import generate_merchant_heatmap

        result = generate_merchant_heatmap([])
        assert result["heatmap"] == []

    def test_patterns_basic(self):
        from app.services.merchant_heatmap import get_merchant_patterns

        txs = self._make_transactions([
            ("Starbucks", 5.0, 0, 8),
            ("Starbucks", 6.0, 1, 8),
            ("Starbucks", 5.0, 2, 8),
        ])

        result = get_merchant_patterns(txs)
        assert len(result["patterns"]) == 1
        p = result["patterns"][0]
        assert p["merchant"] == "Starbucks"
        assert p["transaction_count"] == 3
        assert p["trend"] in ("stable", "increasing", "decreasing")

    def test_patterns_multiple_merchants(self):
        from app.services.merchant_heatmap import get_merchant_patterns

        txs = self._make_transactions([
            ("Amazon", 100.0, 0, 10),
            ("Starbucks", 5.0, 0, 8),
            ("Amazon", 50.0, 1, 10),
        ])

        result = get_merchant_patterns(txs)
        assert len(result["patterns"]) == 2
        # Amazon should be first (highest total)
        assert result["patterns"][0]["merchant"] == "Amazon"

    def test_heatmap_no_merchant(self):
        from app.services.merchant_heatmap import generate_merchant_heatmap

        txs = [{"amount": 10.0, "date": "2025-06-02T10:00:00+00:00"}]
        result = generate_merchant_heatmap(txs, top_n=5)
        # Unknown merchant should be included
        assert len(result["merchants"]) <= 1
