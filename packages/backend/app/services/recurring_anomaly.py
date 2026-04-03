"""
Recurring transaction anomaly detection service.

Detects when recurring expenses deviate from their historical pattern:
- Amount anomaly: expense differs from expected amount by more than threshold
- Timing anomaly: expense generated at unexpected time
- Frequency anomaly: more/fewer occurrences than expected in a period
- Missing anomaly: expected recurring expense not found
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
import statistics


# ─── Config ──────────────────────────────────────────────────────────────────

# Default thresholds (percentage)
AMOUNT_DEVIATION_THRESHOLD = 0.20   # >20% change = anomaly
AMOUNT_LARGE_DEVIATION = 0.50       # >50% change = critical anomaly
MIN_HISTORY_SAMPLES = 3              # need at least 3 occurrences to detect anomalies


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class ExpenseRecord:
    """Lightweight representation of a single expense transaction."""
    id: int
    amount: Decimal
    date: date
    recurring_id: int | None = None
    notes: str = ""


@dataclass
class RecurringConfig:
    """Expected configuration for a recurring expense."""
    id: int
    expected_amount: Decimal
    cadence: str          # DAILY, WEEKLY, MONTHLY, YEARLY
    active: bool = True
    notes: str = ""


@dataclass
class AnomalyAlert:
    """A detected anomaly in a recurring expense pattern."""
    recurring_id: int
    anomaly_type: str           # amount | missing | frequency | timing
    severity: str               # low | medium | high | critical
    message: str
    expected_value: Any = None
    actual_value: Any = None
    affected_expense_id: int | None = None
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "recurring_id": self.recurring_id,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "message": self.message,
            "expected_value": str(self.expected_value) if self.expected_value is not None else None,
            "actual_value": str(self.actual_value) if self.actual_value is not None else None,
            "affected_expense_id": self.affected_expense_id,
            "detected_at": self.detected_at,
        }


# ─── Core detection logic ─────────────────────────────────────────────────────

def detect_amount_anomalies(
    config: RecurringConfig,
    recent_expenses: list[ExpenseRecord],
    threshold: float = AMOUNT_DEVIATION_THRESHOLD,
    critical_threshold: float = AMOUNT_LARGE_DEVIATION,
) -> list[AnomalyAlert]:
    """
    Compare recent expense amounts against expected and historical mean.
    Returns list of AnomalyAlert objects (empty = no anomalies).
    """
    if not recent_expenses:
        return []

    alerts = []
    expected = float(config.expected_amount)

    # Use historical mean if enough samples available
    if len(recent_expenses) >= MIN_HISTORY_SAMPLES:
        historical_amounts = [float(e.amount) for e in recent_expenses[:-1]]  # exclude last
        historical_mean = statistics.mean(historical_amounts)
        baseline = historical_mean
    else:
        baseline = expected

    # Check most recent expense
    latest = recent_expenses[-1]
    actual = float(latest.amount)

    if baseline == 0:
        return []

    deviation = abs(actual - baseline) / baseline

    if deviation >= critical_threshold:
        severity = "critical"
        message = (
            f"Recurring expense #{config.id} amount deviated critically: "
            f"expected ~{baseline:.2f}, got {actual:.2f} "
            f"({deviation*100:.1f}% change)"
        )
    elif deviation >= threshold:
        severity = "high" if deviation >= threshold * 2 else "medium"
        message = (
            f"Recurring expense #{config.id} amount anomaly: "
            f"expected ~{baseline:.2f}, got {actual:.2f} "
            f"({deviation*100:.1f}% change)"
        )
    else:
        return []

    alerts.append(AnomalyAlert(
        recurring_id=config.id,
        anomaly_type="amount",
        severity=severity,
        message=message,
        expected_value=round(baseline, 2),
        actual_value=actual,
        affected_expense_id=latest.id,
    ))
    return alerts


def _expected_period_days(cadence: str) -> int:
    """Return expected number of days between occurrences."""
    return {"DAILY": 1, "WEEKLY": 7, "MONTHLY": 30, "YEARLY": 365}.get(cadence, 30)


def detect_missing_anomalies(
    config: RecurringConfig,
    recent_expenses: list[ExpenseRecord],
    check_date: date | None = None,
) -> list[AnomalyAlert]:
    """
    Detect if a recurring expense is overdue (should have occurred but didn't).
    """
    if not config.active:
        return []

    check_date = check_date or date.today()
    period_days = _expected_period_days(config.cadence)
    tolerance = max(2, period_days // 5)  # 20% tolerance

    if not recent_expenses:
        return []

    last_occurrence = max(e.date for e in recent_expenses)
    days_since = (check_date - last_occurrence).days

    if days_since > period_days + tolerance:
        overdue_by = days_since - period_days
        severity = "high" if overdue_by > period_days else "medium"
        return [AnomalyAlert(
            recurring_id=config.id,
            anomaly_type="missing",
            severity=severity,
            message=(
                f"Recurring expense #{config.id} ({config.cadence}) "
                f"is overdue by {overdue_by} day(s). "
                f"Last occurrence: {last_occurrence.isoformat()}"
            ),
            expected_value=f"occurrence by {(last_occurrence + timedelta(days=period_days)).isoformat()}",
            actual_value=f"not seen as of {check_date.isoformat()}",
        )]
    return []


def detect_frequency_anomalies(
    config: RecurringConfig,
    expenses_last_30_days: list[ExpenseRecord],
) -> list[AnomalyAlert]:
    """
    Detect unexpected frequency: too many or too few occurrences in last 30 days.
    """
    period_days = _expected_period_days(config.cadence)
    expected_count = max(1, round(30 / period_days))
    actual_count = len(expenses_last_30_days)

    if actual_count == 0 or expected_count == 0:
        return []

    ratio = actual_count / expected_count

    if ratio > 2.0:
        return [AnomalyAlert(
            recurring_id=config.id,
            anomaly_type="frequency",
            severity="high",
            message=(
                f"Recurring expense #{config.id} occurred {actual_count}x in 30 days, "
                f"expected ~{expected_count}x (possible duplicate charges)"
            ),
            expected_value=expected_count,
            actual_value=actual_count,
        )]
    elif ratio < 0.4 and expected_count >= 2:
        return [AnomalyAlert(
            recurring_id=config.id,
            anomaly_type="frequency",
            severity="medium",
            message=(
                f"Recurring expense #{config.id} only occurred {actual_count}x in 30 days, "
                f"expected ~{expected_count}x"
            ),
            expected_value=expected_count,
            actual_value=actual_count,
        )]
    return []


def analyze_recurring_expense(
    config: RecurringConfig,
    all_expenses: list[ExpenseRecord],
    check_date: date | None = None,
) -> list[AnomalyAlert]:
    """
    Run all anomaly checks for a single recurring expense config.
    Returns combined list of anomalies.
    """
    if not config.active or not all_expenses:
        return []

    check_date = check_date or date.today()

    # Last 90 days of matching expenses
    cutoff_90 = check_date - timedelta(days=90)
    recent = sorted(
        [e for e in all_expenses if e.date >= cutoff_90],
        key=lambda e: e.date,
    )

    # Last 30 days for frequency check
    cutoff_30 = check_date - timedelta(days=30)
    last_30 = [e for e in recent if e.date >= cutoff_30]

    alerts: list[AnomalyAlert] = []
    alerts.extend(detect_amount_anomalies(config, recent))
    alerts.extend(detect_missing_anomalies(config, recent, check_date=check_date))
    alerts.extend(detect_frequency_anomalies(config, last_30))
    return alerts


def batch_analyze(
    configs: list[RecurringConfig],
    expenses_by_recurring_id: dict[int, list[ExpenseRecord]],
    check_date: date | None = None,
) -> dict[int, list[AnomalyAlert]]:
    """
    Analyze multiple recurring expense configs at once.
    Returns dict mapping recurring_id -> list of anomalies.
    """
    result: dict[int, list[AnomalyAlert]] = {}
    for config in configs:
        expenses = expenses_by_recurring_id.get(config.id, [])
        anomalies = analyze_recurring_expense(config, expenses, check_date=check_date)
        if anomalies:
            result[config.id] = anomalies
    return result


def anomaly_summary(all_anomalies: list[AnomalyAlert]) -> dict:
    """Summarize anomalies by type and severity."""
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for a in all_anomalies:
        by_type[a.anomaly_type] = by_type.get(a.anomaly_type, 0) + 1
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
    return {
        "total": len(all_anomalies),
        "by_type": by_type,
        "by_severity": by_severity,
        "has_critical": by_severity.get("critical", 0) > 0,
    }