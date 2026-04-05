"""Multi-currency & FX conversion support (issue #95)."""
import json, logging, time
from ..extensions import redis_client

logger = logging.getLogger("finmind.fx")
RATES_KEY = "fx:rates"
RATES_TTL = 3600  # 1 hour cache

# Fallback static rates (USD base) — updated manually or via free API
FALLBACK_RATES = {
    "USD": 1.0, "INR": 83.5, "EUR": 0.92, "GBP": 0.79,
    "AED": 3.67, "SGD": 1.34, "AUD": 1.53, "CAD": 1.36,
    "JPY": 149.5, "CHF": 0.90, "CNY": 7.24, "MXN": 17.1,
}


def get_rates(base: str = "USD") -> dict:
    raw = redis_client.get(RATES_KEY)
    if raw:
        cached = json.loads(raw)
        if cached.get("base") == base:
            return cached["rates"]
    return _convert_base(FALLBACK_RATES, base)


def _convert_base(rates_usd: dict, base: str) -> dict:
    if base not in rates_usd: return rates_usd
    base_rate = rates_usd[base]
    return {k: round(v / base_rate, 6) for k, v in rates_usd.items()}


def convert(amount: float, from_currency: str, to_currency: str) -> dict:
    rates = get_rates("USD")
    from_r = rates.get(from_currency.upper())
    to_r = rates.get(to_currency.upper())
    if from_r is None: raise ValueError(f"Unknown currency: {from_currency}")
    if to_r is None: raise ValueError(f"Unknown currency: {to_currency}")
    # Convert via USD base
    usd = amount / from_r
    converted = usd * to_r
    return {
        "from": from_currency.upper(), "to": to_currency.upper(),
        "original": round(amount, 2), "converted": round(converted, 4),
        "rate": round(to_r / from_r, 6),
    }


def normalize_to_base(amounts: list[dict], base_currency: str = "USD") -> dict:
    """
    Normalize a list of {amount, currency} dicts to a common base currency.
    amounts: [{"amount": 100, "currency": "INR"}, ...]
    """
    total = 0.0
    details = []
    for item in amounts:
        result = convert(item["amount"], item["currency"], base_currency)
        total += result["converted"]
        details.append({**item, "converted": result["converted"], "base": base_currency})
    return {"total": round(total, 2), "base": base_currency, "items": details}


def update_rates(rates: dict, base: str = "USD"):
    """Update cached rates (call from background job or admin endpoint)."""
    payload = {"base": base, "rates": rates, "updated_at": time.time()}
    redis_client.setex(RATES_KEY, RATES_TTL, json.dumps(payload))
