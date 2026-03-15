"""Multi-Currency & FX Conversion Service.

Provides exchange-rate management, currency conversion, and
multi-currency analytics for FinMind.  Rates are stored locally
and can be populated manually or via a scheduled fetch from
public FX APIs.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional

from sqlalchemy import func, and_

from ..extensions import db
from ..models import (
    ExchangeRate,
    SupportedCurrency,
    Expense,
    Bill,
    User,
    DEFAULT_CURRENCIES,
)


# ── helpers ──────────────────────────────────────────────

_ZERO = Decimal("0")


def _round_amount(amount: Decimal, decimal_places: int = 2) -> Decimal:
    """Round to the target currency's standard decimal places."""
    fmt = Decimal(10) ** -decimal_places
    return amount.quantize(fmt, rounding=ROUND_HALF_UP)


# ── Currency CRUD ────────────────────────────────────────

def list_currencies(*, active_only: bool = True) -> list[dict]:
    """Return all supported currencies."""
    q = SupportedCurrency.query
    if active_only:
        q = q.filter_by(is_active=True)
    return [
        {
            "code": c.code,
            "name": c.name,
            "symbol": c.symbol,
            "decimal_places": c.decimal_places,
            "is_active": c.is_active,
        }
        for c in q.order_by(SupportedCurrency.code).all()
    ]


def seed_currencies() -> int:
    """Ensure default currencies exist.  Returns count of newly added."""
    added = 0
    for code, name, symbol, dp in DEFAULT_CURRENCIES:
        if not SupportedCurrency.query.get(code):
            db.session.add(
                SupportedCurrency(
                    code=code, name=name, symbol=symbol, decimal_places=dp
                )
            )
            added += 1
    db.session.commit()
    return added


# ── Exchange Rates ───────────────────────────────────────

def set_rate(
    base: str,
    target: str,
    rate: Decimal,
    rate_date: date | None = None,
    source: str = "manual",
) -> dict:
    """Store or update an exchange rate for a given date."""
    rate_date = rate_date or date.today()
    base, target = base.upper(), target.upper()

    existing = ExchangeRate.query.filter_by(
        base_currency=base, target_currency=target, rate_date=rate_date
    ).first()

    if existing:
        existing.rate = rate
        existing.source = source
    else:
        existing = ExchangeRate(
            base_currency=base,
            target_currency=target,
            rate=rate,
            rate_date=rate_date,
            source=source,
        )
        db.session.add(existing)

    # Also store the inverse
    inverse = ExchangeRate.query.filter_by(
        base_currency=target, target_currency=base, rate_date=rate_date
    ).first()
    inv_rate = Decimal("1") / rate if rate else Decimal("0")

    if inverse:
        inverse.rate = inv_rate
        inverse.source = source
    else:
        db.session.add(
            ExchangeRate(
                base_currency=target,
                target_currency=base,
                rate=inv_rate,
                rate_date=rate_date,
                source=source,
            )
        )

    db.session.commit()
    return _rate_to_dict(existing)


def get_rate(
    base: str,
    target: str,
    rate_date: date | None = None,
) -> Optional[dict]:
    """Get exchange rate for a pair, falling back to most recent if date missing."""
    base, target = base.upper(), target.upper()
    if base == target:
        return {
            "base_currency": base,
            "target_currency": target,
            "rate": "1.00000000",
            "rate_date": (rate_date or date.today()).isoformat(),
            "source": "identity",
        }

    if rate_date:
        r = ExchangeRate.query.filter_by(
            base_currency=base, target_currency=target, rate_date=rate_date
        ).first()
        if r:
            return _rate_to_dict(r)

    # Fallback: most recent rate
    r = (
        ExchangeRate.query.filter_by(base_currency=base, target_currency=target)
        .order_by(ExchangeRate.rate_date.desc())
        .first()
    )
    return _rate_to_dict(r) if r else None


def list_rates(
    base: str | None = None,
    target: str | None = None,
    days: int = 30,
) -> list[dict]:
    """List historical rates with optional filters."""
    q = ExchangeRate.query
    cutoff = date.today() - timedelta(days=int(days))
    q = q.filter(ExchangeRate.rate_date >= cutoff)
    if base:
        q = q.filter_by(base_currency=base.upper())
    if target:
        q = q.filter_by(target_currency=target.upper())
    return [
        _rate_to_dict(r)
        for r in q.order_by(ExchangeRate.rate_date.desc()).all()
    ]


def bulk_set_rates(
    base: str, rates: dict[str, Decimal], rate_date: date | None = None, source: str = "bulk"
) -> int:
    """Set multiple rates at once for a base currency. Returns count."""
    count = 0
    for target, rate in rates.items():
        set_rate(base, target, Decimal(str(rate)), rate_date, source)
        count += 1
    return count


# ── Conversion ───────────────────────────────────────────

def convert(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    rate_date: date | None = None,
) -> dict:
    """Convert an amount between currencies."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return {
            "original_amount": str(amount),
            "converted_amount": str(amount),
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": "1.00000000",
            "rate_date": (rate_date or date.today()).isoformat(),
        }

    rate_info = get_rate(from_currency, to_currency, rate_date)
    if not rate_info:
        return None  # No rate available

    rate = Decimal(rate_info["rate"])
    converted = _round_amount(amount * rate)

    return {
        "original_amount": str(amount),
        "converted_amount": str(converted),
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": rate_info["rate"],
        "rate_date": rate_info["rate_date"],
    }


# ── Multi-Currency Analytics ────────────────────────────

def multi_currency_summary(user_id: int, target_currency: str | None = None) -> dict:
    """Aggregate all expenses across currencies into one target currency.

    Returns breakdown by original currency and converted totals.
    """
    user = User.query.get(user_id)
    if not user:
        return None
    target = (target_currency or user.preferred_currency).upper()

    # Expenses grouped by currency
    rows = (
        db.session.query(
            Expense.currency,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter_by(user_id=user_id)
        .group_by(Expense.currency)
        .all()
    )

    breakdown = []
    grand_total = _ZERO

    for currency, total, count in rows:
        original_total = Decimal(str(total))
        if currency.upper() == target:
            converted = original_total
            rate_used = Decimal("1")
        else:
            r = get_rate(currency, target)
            if r:
                rate_used = Decimal(r["rate"])
                converted = _round_amount(original_total * rate_used)
            else:
                rate_used = None
                converted = None

        entry = {
            "currency": currency,
            "original_total": str(original_total),
            "transaction_count": count,
            "converted_total": str(converted) if converted is not None else None,
            "rate_used": str(rate_used) if rate_used is not None else None,
            "target_currency": target,
        }
        breakdown.append(entry)
        if converted is not None:
            grand_total += converted

    # Bills breakdown
    bill_rows = (
        db.session.query(
            Bill.currency,
            func.sum(Bill.amount).label("total"),
            func.count(Bill.id).label("count"),
        )
        .filter_by(user_id=user_id, active=True)
        .group_by(Bill.currency)
        .all()
    )

    bill_breakdown = []
    bill_grand_total = _ZERO

    for currency, total, count in bill_rows:
        original_total = Decimal(str(total))
        if currency.upper() == target:
            converted = original_total
        else:
            r = get_rate(currency, target)
            converted = (
                _round_amount(original_total * Decimal(r["rate"]))
                if r
                else None
            )
        bill_breakdown.append({
            "currency": currency,
            "original_total": str(original_total),
            "bill_count": count,
            "converted_total": str(converted) if converted is not None else None,
        })
        if converted is not None:
            bill_grand_total += converted

    return {
        "target_currency": target,
        "expenses": {
            "breakdown": breakdown,
            "grand_total": str(grand_total),
            "currencies_used": len(breakdown),
        },
        "bills": {
            "breakdown": bill_breakdown,
            "grand_total": str(bill_grand_total),
            "active_currencies": len(bill_breakdown),
        },
    }


# ── helpers ──────────────────────────────────────────────

def _rate_to_dict(r: ExchangeRate) -> dict:
    return {
        "id": r.id,
        "base_currency": r.base_currency,
        "target_currency": r.target_currency,
        "rate": str(r.rate),
        "rate_date": r.rate_date.isoformat(),
        "source": r.source,
    }
