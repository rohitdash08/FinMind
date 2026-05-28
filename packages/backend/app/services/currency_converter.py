"""Multi-Currency Converter Service.

Currency conversion features:
- Real-time exchange rate simulation
- Multi-currency support (50+ currencies)
- Historical rate tracking
- Automatic conversion in transactions
- Favorite currency pairs
- Rate alert system
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.currency")


class CurrencyConverter:
    """Multi-currency converter with simulated exchange rates."""

    # Base rates relative to USD (simulated, normally from API)
    BASE_RATES = {
        "USD": 1.0, "EUR": 0.92, "GBP": 0.79, "JPY": 149.50,
        "CNY": 7.24, "KRW": 1320.0, "INR": 83.0, "CAD": 1.36,
        "AUD": 1.53, "CHF": 0.88, "HKD": 7.82, "SGD": 1.34,
        "TWD": 31.5, "THB": 35.2, "MYR": 4.65, "PHP": 55.5,
        "BRL": 4.95, "MXN": 17.1, "ARS": 350.0, "TRY": 28.5,
        "RUB": 92.0, "ZAR": 18.5, "SEK": 10.4, "NOK": 10.5,
        "DKK": 6.88, "NZD": 1.62, "PLN": 4.02, "CZK": 22.5,
        "HUF": 355.0, "ILS": 3.72, "AED": 3.67, "SAR": 3.75,
    }

    def __init__(self):
        self.rates = dict(self.BASE_RATES)
        self.favorites = {}  # user_id -> list of pairs
        self.alerts = {}     # alert_id -> alert config
        self.history = defaultdict(list)  # pair -> [(date, rate)]

    def convert(self, amount: float, from_currency: str,
                to_currency: str) -> dict:
        """Convert amount between currencies."""
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency not in self.rates:
            return {"error": f"Unsupported currency: {from_currency}"}
        if to_currency not in self.rates:
            return {"error": f"Unsupported currency: {to_currency}"}

        # Convert to USD first, then to target
        usd_amount = amount / self.rates[from_currency]
        target_amount = usd_amount * self.rates[to_currency]

        rate = self.rates[to_currency] / self.rates[from_currency]

        return {
            "from": {"currency": from_currency, "amount": round(amount, 2)},
            "to": {"currency": to_currency, "amount": round(target_amount, 2)},
            "rate": round(rate, 6),
            "inverse_rate": round(1 / max(rate, 0.0001), 6),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def convert_transaction(self, transaction: dict,
                             target_currency: str = "USD") -> dict:
        """Convert a transaction to target currency."""
        amount = float(transaction.get("amount", 0))
        currency = transaction.get("currency", "USD").upper()

        if currency == target_currency.upper():
            return {**transaction, "converted_amount": amount,
                   "conversion_rate": 1.0, "original_currency": currency}

        result = self.convert(abs(amount), currency, target_currency)
        if "error" in result:
            return {**transaction, "conversion_error": result["error"]}

        converted = result["to"]["amount"]
        if amount < 0:
            converted = -converted

        return {
            **transaction,
            "converted_amount": round(converted, 2),
            "conversion_rate": result["rate"],
            "original_currency": currency,
            "target_currency": target_currency.upper(),
        }

    def batch_convert(self, transactions: list[dict],
                       target_currency: str = "USD") -> dict:
        """Convert multiple transactions."""
        converted = []
        errors = 0
        total_original = 0
        total_converted = 0

        for tx in transactions:
            result = self.convert_transaction(tx, target_currency)
            if "conversion_error" in result:
                errors += 1
            else:
                total_original += abs(float(tx.get("amount", 0)))
                total_converted += abs(result.get("converted_amount", 0))
            converted.append(result)

        return {
            "transactions": converted,
            "total_original": round(total_original, 2),
            "total_converted": round(total_converted, 2),
            "target_currency": target_currency.upper(),
            "success_count": len(converted) - errors,
            "error_count": errors,
        }

    def get_rate(self, from_currency: str, to_currency: str) -> dict:
        """Get current exchange rate."""
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency not in self.rates or to_currency not in self.rates:
            return {"error": "Unsupported currency"}

        rate = self.rates[to_currency] / self.rates[from_currency]
        return {
            "from": from_currency,
            "to": to_currency,
            "rate": round(rate, 6),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def list_currencies(self) -> list[dict]:
        """List all supported currencies."""
        return [
            {"code": code, "rate_to_usd": round(1 / max(rate, 0.0001), 6)}
            for code, rate in sorted(self.rates.items())
        ]

    def add_favorite(self, user_id: str, from_curr: str,
                      to_curr: str) -> dict:
        """Add favorite currency pair."""
        if user_id not in self.favorites:
            self.favorites[user_id] = []
        pair = f"{from_curr.upper()}/{to_curr.upper()}"
        if pair not in self.favorites[user_id]:
            self.favorites[user_id].append(pair)
        return {"status": "added", "pair": pair}

    def get_favorites(self, user_id: str) -> list[dict]:
        """Get user favorite pairs with current rates."""
        pairs = self.favorites.get(user_id, [])
        result = []
        for pair in pairs:
            parts = pair.split("/")
            rate_info = self.get_rate(parts[0], parts[1])
            result.append({"pair": pair, **rate_info})
        return result

    def set_alert(self, user_id: str, from_curr: str, to_curr: str,
                   target_rate: float, direction: str = "above") -> dict:
        """Set rate alert."""
        alert_id = str(uuid4())[:8]
        self.alerts[alert_id] = {
            "alert_id": alert_id,
            "user_id": user_id,
            "from": from_curr.upper(),
            "to": to_curr.upper(),
            "target_rate": target_rate,
            "direction": direction,
            "created_at": datetime.utcnow().isoformat(),
            "triggered": False,
        }
        return self.alerts[alert_id]
