"""Multi-currency conversion service with static fallback rates."""

import logging

logger = logging.getLogger("finmind.currency")

# Static exchange rates (USD base) - fallback when no API available
RATES = {
    "USD": 1.0, "INR": 83.5, "EUR": 0.92, "GBP": 0.79, "AED": 3.67,
    "SGD": 1.34, "AUD": 1.53, "CAD": 1.36, "JPY": 149.5, "CHF": 0.88,
    "CNY": 7.24, "KRW": 1320.0, "BRL": 4.97, "MXN": 17.15, "ZAR": 18.6,
    "SEK": 10.45, "NOK": 10.55, "DKK": 6.87, "PLN": 4.02, "THB": 35.2,
    "MYR": 4.72, "IDR": 15650.0, "PHP": 56.0, "VND": 24500.0, "EGP": 30.9,
    "NGN": 1550.0, "KES": 153.0, "GHS": 12.5, "TZS": 2510.0, "PKR": 278.0,
}


def convert(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert amount between currencies."""
    fc = from_currency.upper().strip()
    tc = to_currency.upper().strip()
    if fc not in RATES:
        raise ValueError(f"unsupported currency: {fc}")
    if tc not in RATES:
        raise ValueError(f"unsupported currency: {tc}")
    if fc == tc:
        return {"amount": amount, "from": fc, "to": tc, "rate": 1.0, "converted": amount}
    usd_amount = amount / RATES[fc]
    converted = usd_amount * RATES[tc]
    rate = RATES[tc] / RATES[fc]
    return {
        "amount": round(amount, 2),
        "from": fc,
        "to": tc,
        "rate": round(rate, 6),
        "converted": round(converted, 2),
    }


def get_supported_currencies() -> list:
    return sorted(RATES.keys())


def convert_all(amount: float, from_currency: str) -> list:
    """Convert to all supported currencies."""
    results = []
    for tc in sorted(RATES.keys()):
        if tc != from_currency.upper():
            results.append(convert(amount, from_currency, tc))
    return results
