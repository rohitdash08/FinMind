from __future__ import annotations

import functools
import time
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional

import requests

from sqlalchemy import func

from app.models import Transaction
from app import db

# ---------------------------------------------------------------------------
# FX Rate fetching (Frankfurter.app — ECB rates, no API key required)
# ---------------------------------------------------------------------------

FX_API_BASE = "https://api.frankfurter.app"
_rate_cache: dict[str, tuple[float, float]] = {}  # {pair: (rate, ts)}
_CACHE_TTL = 3600  # 1 hour


def _get_rate(from_currency: str, to_currency: str) -> float:
    """Return the exchange rate from_currency -> to_currency. Cached for 1 hour."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return 1.0

    cache_key = f"{from_currency}_{to_currency}"
    if cache_key in _rate_cache:
        rate, ts = _rate_cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return rate

    try:
        resp = requests.get(
            f"{FX_API_BASE}/latest",
            params={"from": from_currency, "to": to_currency},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"][to_currency])
        _rate_cache[cache_key] = (rate, time.time())
        return rate
    except Exception:
        # Return 1.0 as a safe fallback — better than crashing
        return 1.0


def _get_historical_rate(from_currency: str, to_currency: str, on_date: date) -> float:
    """Return historical FX rate for a specific date."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return 1.0

    date_str = on_date.strftime("%Y-%m-%d")
    cache_key = f"{from_currency}_{to_currency}_{date_str}"
    if cache_key in _rate_cache:
        rate, ts = _rate_cache[cache_key]
        return rate

    try:
        resp = requests.get(
            f"{FX_API_BASE}/{date_str}",
            params={"from": from_currency, "to": to_currency},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"][to_currency])
        _rate_cache[cache_key] = (rate, time.time())
        return rate
    except Exception:
        return 1.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ConvertedTransaction:
    transaction_id: int
    original_amount: float
    original_currency: str
    converted_amount: float
    target_currency: str
    exchange_rate: float
    transaction_date: str  # YYYY-MM-DD


@dataclass
class CurrencyAnalytics:
    currency: str
    total_expenses: float       # in original currency
    total_converted: float      # in target currency
    transaction_count: int
    avg_rate_used: float


@dataclass
class MultiCurrencyResult:
    base_currency: str
    target_currency: str
    total_expenses_converted: float
    total_income_converted: float
    net_converted: float
    analytics_by_currency: list[CurrencyAnalytics]
    recent_rate: float
    rate_date: str


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

def get_multi_currency_summary(
    user_id: int,
    target_currency: str = "USD",
    months: int = 3,
) -> MultiCurrencyResult:
    """
    Convert all transactions to a target currency and return currency-aware analytics.

    Args:
        user_id: JWT user id
        target_currency: target currency code (ISO 4217, default USD)
        months: number of past months to analyze (1-12)
    """
    months = max(1, min(12, months))
    target_currency = target_currency.upper()

    cutoff = date.today() - timedelta(days=months * 31)

    rows = (
        db.session.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
        )
        .all()
    )

    if not rows:
        return MultiCurrencyResult(
            base_currency="USD",
            target_currency=target_currency,
            total_expenses_converted=0.0,
            total_income_converted=0.0,
            net_converted=0.0,
            analytics_by_currency=[],
            recent_rate=1.0,
            rate_date=date.today().strftime("%Y-%m-%d"),
        )

    total_expenses = 0.0
    total_income = 0.0
    by_currency: dict[str, dict] = {}

    for tx in rows:
        # Transactions that have no currency field default to USD
        source_currency = getattr(tx, "currency", None) or "USD"
        source_currency = source_currency.upper()

        try:
            tx_date = tx.date if isinstance(tx.date, date) else date.fromisoformat(str(tx.date))
        except (ValueError, AttributeError):
            tx_date = date.today()

        rate = _get_historical_rate(source_currency, target_currency, tx_date)
        amount = float(tx.amount or 0)
        converted = round(amount * rate, 2)

        if tx.type.lower() == "expense":
            total_expenses += converted
        else:
            total_income += converted

        # Track by currency
        if source_currency not in by_currency:
            by_currency[source_currency] = {
                "expenses": 0.0,
                "expenses_converted": 0.0,
                "income": 0.0,
                "income_converted": 0.0,
                "count": 0,
                "rates": [],
            }
        d = by_currency[source_currency]
        d["count"] += 1
        d["rates"].append(rate)
        if tx.type.lower() == "expense":
            d["expenses"] += amount
            d["expenses_converted"] += converted
        else:
            d["income"] += amount
            d["income_converted"] += converted

    analytics = []
    for currency, d in by_currency.items():
        avg_rate = sum(d["rates"]) / len(d["rates"]) if d["rates"] else 1.0
        analytics.append(
            CurrencyAnalytics(
                currency=currency,
                total_expenses=round(d["expenses"], 2),
                total_converted=round(d["expenses_converted"], 2),
                transaction_count=d["count"],
                avg_rate_used=round(avg_rate, 6),
            )
        )

    # Get current rate for display
    recent_rate = _get_rate("USD", target_currency)
    today_str = date.today().strftime("%Y-%m-%d")

    return MultiCurrencyResult(
        base_currency="USD",
        target_currency=target_currency,
        total_expenses_converted=round(total_expenses, 2),
        total_income_converted=round(total_income, 2),
        net_converted=round(total_income - total_expenses, 2),
        analytics_by_currency=analytics,
        recent_rate=recent_rate,
        rate_date=today_str,
    )


def convert_amount(amount: float, from_currency: str, to_currency: str) -> dict:
    """Simple one-off conversion utility."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    rate = _get_rate(from_currency, to_currency)
    converted = round(amount * rate, 2)
    return {
        "original_amount": amount,
        "original_currency": from_currency,
        "converted_amount": converted,
        "target_currency": to_currency,
        "exchange_rate": rate,
        "rate_date": date.today().strftime("%Y-%m-%d"),
    }