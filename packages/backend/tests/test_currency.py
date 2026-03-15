"""Tests for Multi-Currency & FX Conversion (Issue #95)."""

import pytest
from decimal import Decimal


# ── Helpers ──────────────────────────────────────────────

def _seed(client, hdr):
    """Seed currencies so they're available for rate operations."""
    client.post("/currency/seed", headers=hdr)


def _set_rate(client, hdr, base, target, rate, rate_date=None):
    payload = {"base_currency": base, "target_currency": target, "rate": rate}
    if rate_date:
        payload["rate_date"] = rate_date
    return client.post("/currency/rates", json=payload, headers=hdr)


def _add_expense(client, hdr, amount, currency="INR", notes="test"):
    return client.post(
        "/expenses",
        json={
            "amount": amount,
            "currency": currency,
            "notes": notes,
            "spent_at": "2026-03-10",
        },
        headers=hdr,
    )


# ── Currency List & Seed ─────────────────────────────────

class TestCurrencyList:
    def test_seed_currencies(self, client, auth_header):
        r = client.post("/currency/seed", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["added"] >= 1

    def test_seed_idempotent(self, client, auth_header):
        client.post("/currency/seed", headers=auth_header)
        r = client.post("/currency/seed", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["added"] == 0

    def test_list_currencies(self, client, auth_header):
        _seed(client, auth_header)
        r = client.get("/currency/list", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        codes = [c["code"] for c in data]
        assert "USD" in codes
        assert "INR" in codes
        assert "EUR" in codes

    def test_list_unauthenticated(self, client):
        r = client.get("/currency/list")
        assert r.status_code == 401


# ── Exchange Rates ───────────────────────────────────────

class TestExchangeRates:
    def test_set_rate(self, client, auth_header):
        r = _set_rate(client, auth_header, "USD", "INR", 83.5)
        assert r.status_code == 200
        data = r.get_json()
        assert data["base_currency"] == "USD"
        assert data["target_currency"] == "INR"
        assert float(data["rate"]) == pytest.approx(83.5)

    def test_set_rate_creates_inverse(self, client, auth_header):
        _set_rate(client, auth_header, "USD", "INR", 83.5)
        r = client.get("/currency/rates/INR/USD", headers=auth_header)
        assert r.status_code == 200
        rate = float(r.get_json()["rate"])
        expected = 1 / 83.5
        assert rate == pytest.approx(expected, rel=1e-4)

    def test_set_rate_with_date(self, client, auth_header):
        r = _set_rate(client, auth_header, "EUR", "USD", 1.08, "2026-03-01")
        assert r.status_code == 200
        assert r.get_json()["rate_date"] == "2026-03-01"

    def test_set_rate_update(self, client, auth_header):
        _set_rate(client, auth_header, "USD", "EUR", 0.92)
        r = _set_rate(client, auth_header, "USD", "EUR", 0.93)
        assert r.status_code == 200
        assert float(r.get_json()["rate"]) == pytest.approx(0.93)

    def test_set_rate_invalid(self, client, auth_header):
        r = client.post(
            "/currency/rates",
            json={"base_currency": "USD", "target_currency": "EUR"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_set_rate_negative(self, client, auth_header):
        r = _set_rate(client, auth_header, "USD", "EUR", -1.5)
        assert r.status_code == 400

    def test_get_rate_identity(self, client, auth_header):
        r = client.get("/currency/rates/USD/USD", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["rate"] == "1.00000000"

    def test_get_rate_not_found(self, client, auth_header):
        r = client.get("/currency/rates/XYZ/ABC", headers=auth_header)
        assert r.status_code == 404

    def test_list_rates(self, client, auth_header):
        _set_rate(client, auth_header, "USD", "INR", 83.5)
        _set_rate(client, auth_header, "EUR", "INR", 90.2)
        r = client.get("/currency/rates", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        # At least 4 rates (2 pairs × 2 directions)
        assert len(data) >= 4

    def test_list_rates_filtered(self, client, auth_header):
        _set_rate(client, auth_header, "USD", "INR", 83.5)
        _set_rate(client, auth_header, "EUR", "INR", 90.2)
        r = client.get("/currency/rates?base=USD", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert all(r["base_currency"] == "USD" for r in data)

    def test_bulk_set_rates(self, client, auth_header):
        r = client.post(
            "/currency/rates/bulk",
            json={
                "base_currency": "USD",
                "rates": {"EUR": 0.92, "GBP": 0.79, "INR": 83.5},
            },
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["updated"] == 3


# ── Conversion ───────────────────────────────────────────

class TestConversion:
    def test_convert_same_currency(self, client, auth_header):
        r = client.post(
            "/currency/convert",
            json={"amount": 100, "from": "USD", "to": "USD"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["converted_amount"] == "100"
        assert data["rate"] == "1.00000000"

    def test_convert_with_rate(self, client, auth_header):
        _set_rate(client, auth_header, "USD", "INR", 83.5)
        r = client.post(
            "/currency/convert",
            json={"amount": 100, "from": "USD", "to": "INR"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert float(data["converted_amount"]) == pytest.approx(8350.0)

    def test_convert_no_rate(self, client, auth_header):
        r = client.post(
            "/currency/convert",
            json={"amount": 100, "from": "XYZ", "to": "ABC"},
            headers=auth_header,
        )
        assert r.status_code == 404

    def test_convert_missing_fields(self, client, auth_header):
        r = client.post(
            "/currency/convert",
            json={"amount": 100},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_convert_inverse(self, client, auth_header):
        _set_rate(client, auth_header, "USD", "INR", 83.5)
        r = client.post(
            "/currency/convert",
            json={"amount": 8350, "from": "INR", "to": "USD"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert float(data["converted_amount"]) == pytest.approx(100.0, rel=0.01)


# ── Multi-Currency Summary ───────────────────────────────

class TestMultiCurrencySummary:
    def test_summary_empty(self, client, auth_header):
        r = client.get("/currency/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["expenses"]["currencies_used"] == 0
        assert data["expenses"]["grand_total"] == "0"

    def test_summary_single_currency(self, client, auth_header):
        _add_expense(client, auth_header, 500, "INR")
        _add_expense(client, auth_header, 300, "INR")
        r = client.get("/currency/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["target_currency"] == "INR"
        assert data["expenses"]["currencies_used"] == 1
        assert float(data["expenses"]["grand_total"]) == 800.0

    def test_summary_multi_currency(self, client, auth_header):
        _set_rate(client, auth_header, "USD", "INR", 83.5)
        _add_expense(client, auth_header, 1000, "INR")
        _add_expense(client, auth_header, 100, "USD")
        r = client.get("/currency/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["expenses"]["currencies_used"] == 2
        total = float(data["expenses"]["grand_total"])
        # 1000 INR + 100 USD * 83.5 = 1000 + 8350 = 9350
        assert total == pytest.approx(9350.0)

    def test_summary_override_target(self, client, auth_header):
        _set_rate(client, auth_header, "INR", "USD", 0.012)
        _add_expense(client, auth_header, 1000, "INR")
        r = client.get("/currency/summary?target=USD", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["target_currency"] == "USD"
        total = float(data["expenses"]["grand_total"])
        assert total == pytest.approx(12.0)
