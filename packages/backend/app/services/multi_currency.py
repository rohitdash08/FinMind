"""Multi-currency expense tracking.

Manages exchange rates, converts expenses to a base currency,
and provides multi-currency portfolio views.
"""

from datetime import datetime, date
from collections import defaultdict
from ..extensions import db


class ExchangeRate(db.Model):
    __tablename__ = "exchange_rates"
    id = db.Column(db.Integer, primary_key=True)
    base_currency = db.Column(db.String(3), nullable=False)
    target_currency = db.Column(db.String(3), nullable=False)
    rate = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("base_currency", "target_currency", "date"),)


class UserCurrencyPreference(db.Model):
    __tablename__ = "user_currency_preferences"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    base_currency = db.Column(db.String(3), nullable=False, default="USD")
    display_currencies = db.Column(db.Text, default="")  # comma-separated


def get_user_currency(user_id: int) -> dict:
    pref = UserCurrencyPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        return {"base_currency": "USD", "display_currencies": []}
    return {
        "base_currency": pref.base_currency,
        "display_currencies": [c.strip() for c in pref.display_currencies.split(",") if c.strip()],
    }


def set_user_currency(user_id: int, base_currency: str, display_currencies: list[str] | None = None) -> dict:
    base_currency = base_currency.upper().strip()
    if len(base_currency) != 3:
        raise ValueError("Currency code must be 3 characters (ISO 4217)")

    pref = UserCurrencyPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        pref = UserCurrencyPreference(user_id=user_id)
        db.session.add(pref)
    pref.base_currency = base_currency
    if display_currencies is not None:
        pref.display_currencies = ",".join(c.upper().strip() for c in display_currencies)
    db.session.commit()
    return get_user_currency(user_id)


def set_exchange_rate(base: str, target: str, rate: float, rate_date: date | None = None) -> dict:
    base = base.upper().strip()
    target = target.upper().strip()
    rate_date = rate_date or date.today()

    if rate <= 0:
        raise ValueError("Rate must be positive")

    existing = ExchangeRate.query.filter_by(base_currency=base, target_currency=target, date=rate_date).first()
    if existing:
        existing.rate = rate
        existing.updated_at = datetime.utcnow()
    else:
        existing = ExchangeRate(base_currency=base, target_currency=target, rate=rate, date=rate_date)
        db.session.add(existing)
    db.session.commit()
    return _serialize_rate(existing)


def get_exchange_rate(base: str, target: str, rate_date: date | None = None) -> float | None:
    base = base.upper().strip()
    target = target.upper().strip()
    if base == target:
        return 1.0

    q = ExchangeRate.query.filter_by(base_currency=base, target_currency=target)
    if rate_date:
        q = q.filter(ExchangeRate.date <= rate_date)
    rate_obj = q.order_by(ExchangeRate.date.desc()).first()

    if rate_obj:
        return rate_obj.rate

    # Try inverse
    q2 = ExchangeRate.query.filter_by(base_currency=target, target_currency=base)
    if rate_date:
        q2 = q2.filter(ExchangeRate.date <= rate_date)
    inv = q2.order_by(ExchangeRate.date.desc()).first()
    if inv and inv.rate > 0:
        return round(1.0 / inv.rate, 6)

    return None


def convert_amount(amount: float, from_currency: str, to_currency: str, rate_date: date | None = None) -> dict:
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()

    if from_currency == to_currency:
        return {"original": amount, "converted": amount, "from": from_currency, "to": to_currency, "rate": 1.0}

    rate = get_exchange_rate(from_currency, to_currency, rate_date)
    if rate is None:
        raise ValueError(f"No exchange rate found for {from_currency} -> {to_currency}")

    return {
        "original": amount,
        "converted": round(amount * rate, 2),
        "from": from_currency,
        "to": to_currency,
        "rate": rate,
    }


def list_rates(base: str | None = None, rate_date: date | None = None) -> list[dict]:
    q = ExchangeRate.query
    if base:
        q = q.filter_by(base_currency=base.upper())
    if rate_date:
        q = q.filter_by(date=rate_date)
    else:
        q = q.order_by(ExchangeRate.date.desc())
    return [_serialize_rate(r) for r in q.limit(100).all()]


def multi_currency_summary(user_id: int, expenses: list[dict]) -> dict:
    """Convert a list of expenses to the user's base currency and summarize."""
    pref = get_user_currency(user_id)
    base = pref["base_currency"]

    converted = []
    total_base = 0
    by_currency = defaultdict(float)
    errors = []

    for exp in expenses:
        currency = exp.get("currency", base)
        amount = float(exp.get("amount", 0))
        by_currency[currency] += amount

        if currency == base:
            converted.append({**exp, "base_amount": amount, "base_currency": base})
            total_base += amount
        else:
            try:
                result = convert_amount(amount, currency, base)
                converted.append({**exp, "base_amount": result["converted"], "base_currency": base, "rate_used": result["rate"]})
                total_base += result["converted"]
            except ValueError:
                errors.append(f"No rate for {currency} -> {base}")
                converted.append({**exp, "base_amount": None, "base_currency": base})

    return {
        "base_currency": base,
        "total_in_base": round(total_base, 2),
        "by_currency": dict(by_currency),
        "expenses": converted,
        "conversion_errors": errors,
    }


def _serialize_rate(r: ExchangeRate) -> dict:
    return {
        "id": r.id,
        "base_currency": r.base_currency,
        "target_currency": r.target_currency,
        "rate": r.rate,
        "date": r.date.isoformat(),
    }
