"""
Anomaly Detection Engine — FinMind (#72)

Detects unusual spending spikes by category or merchant using
z-score statistical analysis against a rolling baseline.
Returns ranked anomalies with explanation metadata.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.anomaly_detection")

# ── Tuneable thresholds ────────────────────────────────────────────────────────
Z_SCORE_HIGH = 2.5       # z-score >= 2.5 → high severity anomaly
Z_SCORE_MEDIUM = 1.5     # z-score >= 1.5 → medium severity anomaly
MIN_BASELINE_MONTHS = 2  # need at least 2 prior months to compute baseline
MIN_ABSOLUTE_SPIKE = Decimal("100")  # minimum absolute spike to report (INR)
BASELINE_MONTHS = 3      # how many prior months to use for baseline


class AnomalyResult(TypedDict):
    id: str
    type: str               # "category" | "merchant"
    label: str              # category name or merchant name
    category_id: int | None
    current_spend: float
    baseline_avg: float
    baseline_stddev: float
    z_score: float
    spike_amount: float     # how much above the mean
    spike_percent: float    # % above the mean
    severity: str           # "high" | "medium" | "low"
    explanation: str


# ── Internal helpers ───────────────────────────────────────────────────────────

def _period_dates(ym: str) -> tuple[date, date]:
    """Return (first_day, last_day) for a YYYY-MM string."""
    year, month = int(ym[:4]), int(ym[5:7])
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


def _prior_months(ym: str, n: int) -> list[str]:
    """Return the n month strings preceding ym."""
    year, month = int(ym[:4]), int(ym[5:7])
    result: list[str] = []
    for _ in range(n):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        result.append(f"{year:04d}-{month:02d}")
    return result


def _month_category_spend(uid: int, ym: str) -> dict[int, dict]:
    """Aggregated spend per category for one month.

    Returns { category_id: { "name": str, "total": Decimal } }
    """
    year, month = int(ym[:4]), int(ym[5:7])
    rows = (
        db.session.query(
            Expense.category_id,
            Category.name,
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(Category, Category.id == Expense.category_id)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
        .group_by(Expense.category_id, Category.name)
        .all()
    )
    return {
        r.category_id: {"name": r.name or "Uncategorized", "total": Decimal(str(r.total))}
        for r in rows
    }


def _month_merchant_spend(uid: int, ym: str) -> dict[str, Decimal]:
    """Aggregated spend per merchant (notes field) for one month."""
    year, month = int(ym[:4]), int(ym[5:7])
    rows = (
        db.session.query(
            Expense.notes,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.notes.isnot(None),
            Expense.notes != "",
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
        .group_by(Expense.notes)
        .all()
    )
    return {r.notes: Decimal(str(r.total)) for r in rows if r.notes}


def _compute_stats(values: list[Decimal]) -> tuple[float, float]:
    """Return (mean, stddev) from a list of Decimal values."""
    if not values:
        return 0.0, 0.0
    floats = [float(v) for v in values]
    n = len(floats)
    mean = sum(floats) / n
    if n == 1:
        # With a single data point, use mean as stddev estimate (conservative)
        return mean, mean * 0.3 if mean > 0 else 1.0
    variance = sum((x - mean) ** 2 for x in floats) / (n - 1)  # sample variance
    stddev = math.sqrt(variance) if variance > 0 else mean * 0.1
    return mean, stddev


def _severity(z_score: float) -> str:
    if z_score >= Z_SCORE_HIGH:
        return "high"
    if z_score >= Z_SCORE_MEDIUM:
        return "medium"
    return "low"


def _explanation_category(label: str, current: float, avg: float, pct: float) -> str:
    return (
        f"Your spending on '{label}' this month ({current:.0f}) is "
        f"{pct:.0f}% above your {BASELINE_MONTHS}-month average ({avg:.0f}). "
        f"This is an unusual spike worth reviewing."
    )


def _explanation_merchant(label: str, current: float, avg: float, pct: float) -> str:
    return (
        f"Spending at '{label}' this month ({current:.0f}) is "
        f"{pct:.0f}% above your typical amount ({avg:.0f}). "
        f"Check if this is an expected one-off or a recurring change."
    )


# ── Category anomaly detection ─────────────────────────────────────────────────

def _detect_category_anomalies(uid: int, ym: str, prior_yms: list[str]) -> list[AnomalyResult]:
    current = _month_category_spend(uid, ym)
    if not current:
        return []

    # Build per-category baseline from prior months
    baseline: dict[int, list[Decimal]] = {}
    for pym in prior_yms:
        month_data = _month_category_spend(uid, pym)
        for cat_id, info in month_data.items():
            baseline.setdefault(cat_id, []).append(info["total"])

    anomalies: list[AnomalyResult] = []
    for cat_id, info in current.items():
        hist = baseline.get(cat_id, [])
        if len(hist) < 1:
            # No history at all — skip (could be a new category)
            continue

        mean, stddev = _compute_stats(hist)
        if mean == 0:
            continue

        current_val = float(info["total"])
        z = (current_val - mean) / stddev if stddev > 0 else 0.0
        spike = current_val - mean
        spike_pct = (spike / mean) * 100.0

        # Only flag upward anomalies above minimum absolute threshold
        if z < Z_SCORE_MEDIUM or Decimal(str(spike)) < MIN_ABSOLUTE_SPIKE:
            continue

        sev = _severity(z)
        label = info["name"]
        anomaly_id = f"cat_anomaly_{cat_id}_{ym}"

        anomalies.append(AnomalyResult(
            id=anomaly_id,
            type="category",
            label=label,
            category_id=cat_id,
            current_spend=round(current_val, 2),
            baseline_avg=round(mean, 2),
            baseline_stddev=round(stddev, 2),
            z_score=round(z, 2),
            spike_amount=round(spike, 2),
            spike_percent=round(spike_pct, 1),
            severity=sev,
            explanation=_explanation_category(label, current_val, mean, spike_pct),
        ))

    return anomalies


# ── Merchant anomaly detection ─────────────────────────────────────────────────

def _detect_merchant_anomalies(uid: int, ym: str, prior_yms: list[str]) -> list[AnomalyResult]:
    current = _month_merchant_spend(uid, ym)
    if not current:
        return []

    baseline: dict[str, list[Decimal]] = {}
    for pym in prior_yms:
        month_data = _month_merchant_spend(uid, pym)
        for merchant, total in month_data.items():
            baseline.setdefault(merchant, []).append(total)

    anomalies: list[AnomalyResult] = []
    for merchant, cur_total in current.items():
        hist = baseline.get(merchant, [])
        if len(hist) < 1:
            continue

        mean, stddev = _compute_stats(hist)
        if mean == 0:
            continue

        current_val = float(cur_total)
        z = (current_val - mean) / stddev if stddev > 0 else 0.0
        spike = current_val - mean
        spike_pct = (spike / mean) * 100.0

        if z < Z_SCORE_MEDIUM or Decimal(str(spike)) < MIN_ABSOLUTE_SPIKE:
            continue

        sev = _severity(z)
        # Use a slug-safe ID
        merchant_slug = merchant.lower().replace(" ", "_")[:30]
        anomaly_id = f"merch_anomaly_{merchant_slug}_{ym}"

        anomalies.append(AnomalyResult(
            id=anomaly_id,
            type="merchant",
            label=merchant,
            category_id=None,
            current_spend=round(current_val, 2),
            baseline_avg=round(mean, 2),
            baseline_stddev=round(stddev, 2),
            z_score=round(z, 2),
            spike_amount=round(spike, 2),
            spike_percent=round(spike_pct, 1),
            severity=sev,
            explanation=_explanation_merchant(merchant, current_val, mean, spike_pct),
        ))

    return anomalies


# ── Public API ─────────────────────────────────────────────────────────────────

def detect_anomalies(uid: int, ym: str) -> dict:
    """Detect spending anomalies for *uid* in month *ym* (YYYY-MM).

    Returns a dict with:
      - month: the queried month
      - anomalies_count: total anomalies found
      - has_high_severity: bool shortcut
      - anomalies: list of AnomalyResult dicts, sorted by severity then z_score desc
    """
    prior_yms = _prior_months(ym, BASELINE_MONTHS)

    cat_anomalies = _detect_category_anomalies(uid, ym, prior_yms)
    merch_anomalies = _detect_merchant_anomalies(uid, ym, prior_yms)

    all_anomalies = cat_anomalies + merch_anomalies

    # Sort: high first, then by z_score descending
    sev_order = {"high": 0, "medium": 1, "low": 2}
    all_anomalies.sort(key=lambda a: (sev_order.get(a["severity"], 3), -a["z_score"]))

    has_high = any(a["severity"] == "high" for a in all_anomalies)

    logger.info(
        "anomaly_detection uid=%d month=%s found=%d (high=%s)",
        uid, ym, len(all_anomalies), has_high,
    )

    return {
        "month": ym,
        "anomalies_count": len(all_anomalies),
        "has_high_severity": has_high,
        "anomalies": list(all_anomalies),
    }