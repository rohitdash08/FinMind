"""
Subscription cost increase detection service.

Detects when the cost of a subscription has increased compared to
previous charges, notifying users of price changes.

Integrates with RecurringExpense model (cadence=MONTHLY/YEARLY, notes like "Netflix", "Spotify").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any


# ─── Configuration ───────────────────────────────────────────────────────────

# Default thresholds
DEFAULT_INCREASE_THRESHOLD = Decimal("0.01")   # Any increase > 1 cent
SIGNIFICANT_INCREASE_PCT = Decimal("0.10")     # >= 10% = significant
LARGE_INCREASE_PCT = Decimal("0.25")           # >= 25% = large / high severity


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class ChargeRecord:
    """A single subscription charge occurrence."""
    id: int
    amount: Decimal
    charge_date: date
    subscription_id: int


@dataclass
class SubscriptionConfig:
    """Subscription definition (maps to a RecurringExpense)."""
    id: int
    name: str                    # e.g., "Netflix", "Spotify Premium"
    expected_amount: Decimal     # Last known / configured amount
    cadence: str                 # MONTHLY, YEARLY, etc.
    currency: str = "USD"
    active: bool = True


@dataclass
class PriceChangeAlert:
    """Alert generated when a subscription price changes."""
    subscription_id: int
    subscription_name: str
    old_amount: Decimal
    new_amount: Decimal
    change_pct: Decimal
    severity: str               # info | medium | high | critical
    message: str
    affected_charge_id: int | None = None
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def increase_amount(self) -> Decimal:
        return self.new_amount - self.old_amount

    def to_dict(self) -> dict:
        return {
            "subscription_id": self.subscription_id,
            "subscription_name": self.subscription_name,
            "old_amount": str(self.old_amount),
            "new_amount": str(self.new_amount),
            "change_amount": str(self.increase_amount),
            "change_pct": f"{self.change_pct * 100:.1f}%",
            "severity": self.severity,
            "message": self.message,
            "affected_charge_id": self.affected_charge_id,
            "detected_at": self.detected_at,
        }


# ─── Core detection logic ─────────────────────────────────────────────────────

def _severity(change_pct: Decimal) -> str:
    if change_pct >= LARGE_INCREASE_PCT:
        return "high"
    if change_pct >= SIGNIFICANT_INCREASE_PCT:
        return "medium"
    return "info"


def detect_price_increase(
    config: SubscriptionConfig,
    charges: list[ChargeRecord],
    min_history: int = 2,
) -> list[PriceChangeAlert]:
    """
    Compare consecutive subscription charges to detect price increases.

    Algorithm:
    1. Sort charges by date ascending.
    2. Compare each consecutive pair: (prev_amount, current_amount).
    3. If current > prev + DEFAULT_INCREASE_THRESHOLD, emit an alert.
    4. Also check most recent charge vs config.expected_amount.

    Returns list of PriceChangeAlert (newest first).
    """
    if not config.active or len(charges) < 1:
        return []

    sorted_charges = sorted(charges, key=lambda c: c.charge_date)
    alerts: list[PriceChangeAlert] = []

    # Consecutive pair analysis
    for i in range(1, len(sorted_charges)):
        prev = sorted_charges[i - 1]
        curr = sorted_charges[i]

        if curr.amount <= prev.amount:
            continue  # No increase, skip

        increase = curr.amount - prev.amount
        if increase < DEFAULT_INCREASE_THRESHOLD:
            continue  # Rounding noise

        if prev.amount == 0:
            continue  # Avoid division by zero

        change_pct = increase / prev.amount
        severity = _severity(change_pct)

        alerts.append(PriceChangeAlert(
            subscription_id=config.id,
            subscription_name=config.name,
            old_amount=prev.amount,
            new_amount=curr.amount,
            change_pct=change_pct,
            severity=severity,
            message=(
                f"'{config.name}' price increased from {config.currency} {prev.amount:.2f} "
                f"to {config.currency} {curr.amount:.2f} "
                f"(+{change_pct * 100:.1f}%, +{config.currency} {increase:.2f})"
            ),
            affected_charge_id=curr.id,
        ))

    # Sort newest first
    alerts.sort(key=lambda a: a.detected_at, reverse=True)
    return alerts


def detect_vs_expected(
    config: SubscriptionConfig,
    latest_charge: ChargeRecord | None,
) -> PriceChangeAlert | None:
    """
    Check if the most recent charge differs from the configured expected amount.
    Useful when expected_amount was manually set or imported.
    """
    if latest_charge is None or not config.active:
        return None

    if latest_charge.amount <= config.expected_amount:
        return None  # Same or cheaper

    increase = latest_charge.amount - config.expected_amount
    if increase < DEFAULT_INCREASE_THRESHOLD:
        return None

    if config.expected_amount == 0:
        return None

    change_pct = increase / config.expected_amount
    severity = _severity(change_pct)

    return PriceChangeAlert(
        subscription_id=config.id,
        subscription_name=config.name,
        old_amount=config.expected_amount,
        new_amount=latest_charge.amount,
        change_pct=change_pct,
        severity=severity,
        message=(
            f"'{config.name}' latest charge ({latest_charge.amount:.2f}) "
            f"exceeds configured amount ({config.expected_amount:.2f}) "
            f"by +{change_pct * 100:.1f}%"
        ),
        affected_charge_id=latest_charge.id,
    )


def scan_all_subscriptions(
    configs: list[SubscriptionConfig],
    charges_by_id: dict[int, list[ChargeRecord]],
) -> list[PriceChangeAlert]:
    """
    Scan all subscriptions for price increases.
    Returns sorted list of alerts (critical/high first).
    """
    all_alerts: list[PriceChangeAlert] = []

    for config in configs:
        charges = sorted(charges_by_id.get(config.id, []), key=lambda c: c.charge_date)

        # Consecutive increase detection
        alerts = detect_price_increase(config, charges)
        all_alerts.extend(alerts)

        # Also check vs expected
        latest = charges[-1] if charges else None
        vs_expected = detect_vs_expected(config, latest)
        if vs_expected:
            # Avoid duplicating if already found via consecutive check
            already_found = any(
                a.affected_charge_id == vs_expected.affected_charge_id
                and a.subscription_id == vs_expected.subscription_id
                for a in alerts
            )
            if not already_found:
                all_alerts.append(vs_expected)

    # Sort by severity
    sev_order = {"high": 3, "medium": 2, "info": 1}
    all_alerts.sort(key=lambda a: sev_order.get(a.severity, 0), reverse=True)
    return all_alerts


def price_change_summary(alerts: list[PriceChangeAlert]) -> dict:
    """High-level summary of price change alerts."""
    by_severity: dict[str, int] = {}
    total_extra_spend = Decimal("0")
    for a in alerts:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
        total_extra_spend += a.increase_amount
    return {
        "total_alerts": len(alerts),
        "by_severity": by_severity,
        "total_extra_monthly_spend": str(total_extra_spend.quantize(Decimal("0.01"))),
        "has_high_severity": by_severity.get("high", 0) > 0,
    }