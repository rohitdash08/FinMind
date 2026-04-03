"""Multi-currency FX conversion service for FinMind (#95)."""
import logging
import json
from datetime import date, datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from typing import Optional

from ..extensions import db

logger = logging.getLogger("finmind.fx")

# Static fallback rates (relative to INR base, as FinMind defaults to INR)
# Updated: 2026-Q1 approximate rates
_STATIC_RATES_INR: dict[str, float] = {
    "INR": 1.0,
    "USD": 83.5,
    "EUR": 90.2,
    "GBP": 105.3,
    "JPY": 0.56,
    "CNY": 11.5,
    "AED": 22.7,
    "SGD": 62.0,
    "CAD": 61.5,
    "AUD": 53.8,
    "CHF": 94.0,
    "HKD": 10.7,
    "MYR": 18.5,
    "THB": 2.3,
    "IDR": 0.0053,
    "PHP": 1.46,
    "VND": 0.0034,
    "KRW": 0.063,
    "BRL": 16.8,
    "MXN": 4.9,
    "ZAR": 4.6,
    "NGN": 0.057,
    "GHS": 5.7,
    "KES": 0.65,
    "EGP": 1.7,
    "SAR": 22.3,
    "QAR": 22.9,
    "KWD": 272.0,
    "BHD": 221.0,
    "OMR": 216.0,
    "TRY": 2.6,
    "RUB": 0.93,
    "PKR": 0.30,
    "BDT": 0.75,
    "LKR": 0.28,
    "NPR": 0.63,
    "MMK": 0.040,
    "NZD": 50.0,
    "SEK": 8.0,
    "NOK": 7.8,
    "DKK": 12.1,
    "PLN": 21.3,
    "CZK": 3.7,
    "HUF": 0.23,
}

# Rate cache: {date_str: {from_currency: {to_currency: rate}}}
_rate_cache: dict[str, dict] = {}
_CACHE_TTL_HOURS = 6


def _cache_key(from_currency: str, to_currency: str, date_str: str) -> str:
    return f"{date_str}:{from_currency}:{to_currency}"


def _get_cached_rate(from_cur: str, to_cur: str, date_str: str) -> Optional[float]:
    key = _cache_key(from_cur, to_cur, date_str)
    return _rate_cache.get(key)


def _set_cached_rate(from_cur: str, to_cur: str, date_str: str, rate: float):
    key = _cache_key(from_cur, to_cur, date_str)
    _rate_cache[key] = rate


def _fetch_live_rate(from_currency: str, to_currency: str) -> Optional[float]:
    """Try to fetch live rate from exchangerate-api.com (free tier, no key required for basic)."""
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
        req = Request(url, headers={"User-Agent": "FinMind/1.0"})
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            rates = data.get("rates", {})
            if to_currency in rates:
                return float(rates[to_currency])
    except (URLError, HTTPError, json.JSONDecodeError, Exception) as e:
        logger.debug("Live FX fetch failed %s->%s: %s", from_currency, to_currency, e)
    return None


def get_exchange_rate(
    from_currency: str,
    to_currency: str,
    target_date: Optional[date] = None,
    use_live: bool = True,
) -> dict:
    """
    Get exchange rate between two currencies.

    Args:
        from_currency: Source currency code (e.g. "USD")
        to_currency: Target currency code (e.g. "INR")
        target_date: Date for historical rate (defaults to today)
        use_live: Whether to attempt live API call first

    Returns:
        {
            "from_currency": "USD",
            "to_currency": "INR",
            "rate": 83.5,
            "date": "2026-04-03",
            "source": "live" | "cache" | "static"
        }
    """
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()

    if from_currency == to_currency:
        return {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": 1.0,
            "date": str(target_date or date.today()),
            "source": "identity",
        }

    date_str = str(target_date or date.today())

    # Check cache
    cached = _get_cached_rate(from_currency, to_currency, date_str)
    if cached is not None:
        return {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": cached,
            "date": date_str,
            "source": "cache",
        }

    # Try live rate (today only)
    rate = None
    source = "static"
    if use_live and (target_date is None or target_date == date.today()):
        rate = _fetch_live_rate(from_currency, to_currency)
        if rate is not None:
            source = "live"
            _set_cached_rate(from_currency, to_currency, date_str, rate)

    # Fallback to static rates via INR as intermediate
    if rate is None:
        from_inr = _STATIC_RATES_INR.get(from_currency)
        to_inr = _STATIC_RATES_INR.get(to_currency)
        if from_inr is None or to_inr is None:
            raise ValueError(f"Unsupported currency: {from_currency if from_inr is None else to_currency}")
        rate = to_inr / from_inr
        _set_cached_rate(from_currency, to_currency, date_str, rate)

    logger.info("FX rate %s->%s = %.4f (source=%s)", from_currency, to_currency, rate, source)
    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": round(rate, 6),
        "date": date_str,
        "source": source,
    }


def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str,
    target_date: Optional[date] = None,
) -> dict:
    """
    Convert an amount from one currency to another.

    Returns:
        {
            "original_amount": float,
            "converted_amount": float,
            "from_currency": str,
            "to_currency": str,
            "rate": float,
            "date": str,
            "source": str
        }
    """
    rate_info = get_exchange_rate(from_currency, to_currency, target_date)
    converted = round(amount * rate_info["rate"], 2)
    return {
        "original_amount": amount,
        "converted_amount": converted,
        "from_currency": rate_info["from_currency"],
        "to_currency": rate_info["to_currency"],
        "rate": rate_info["rate"],
        "date": rate_info["date"],
        "source": rate_info["source"],
    }


def list_supported_currencies() -> list[dict]:
    """List all supported currency codes with INR base rates."""
    return [
        {"code": code, "rate_vs_inr": rate}
        for code, rate in sorted(_STATIC_RATES_INR.items())
    ]


def normalize_to_base(
    uid: int,
    amounts: list[dict],
    base_currency: str = "INR",
) -> list[dict]:
    """
    Normalize a list of {amount, currency} dicts to a single base currency.

    Args:
        uid: User ID (for future user-preference lookup)
        amounts: List of {"amount": float, "currency": str}
        base_currency: Target currency for normalization

    Returns:
        List of converted amounts with original values preserved
    """
    results = []
    for item in amounts:
        amount = float(item.get("amount", 0))
        currency = (item.get("currency") or base_currency).upper()
        if currency == base_currency:
            results.append({
                **item,
                "base_amount": amount,
                "base_currency": base_currency,
                "rate": 1.0,
            })
        else:
            conversion = convert_amount(amount, currency, base_currency)
            results.append({
                **item,
                "base_amount": conversion["converted_amount"],
                "base_currency": base_currency,
                "rate": conversion["rate"],
            })
    return results

