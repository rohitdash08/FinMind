"""Auto-detect subscriptions from recurring transaction patterns.

Analyzes expense history to identify subscription services by looking for:
  - Repeated merchant names with similar amounts
  - Regular time intervals (weekly, monthly, yearly)
  - Known subscription service name patterns

Confidence scoring considers:
  - Number of occurrences (more = higher confidence)
  - Amount consistency (same amount = higher confidence)
  - Interval regularity (consistent cadence = higher confidence)
"""

import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import DetectedSubscription, Expense

logger = logging.getLogger("finmind.subscription_detection")

# Known subscription service patterns (case-insensitive)
KNOWN_SERVICES = [
    r"netflix",
    r"spotify",
    r"amazon\s*prime",
    r"disney\s*\+?",
    r"hulu",
    r"apple\s*(music|tv|one|icloud|storage)",
    r"google\s*(one|storage|workspace|cloud)",
    r"microsoft\s*(365|office)",
    r"adobe",
    r"dropbox",
    r"slack",
    r"zoom",
    r"github",
    r"chatgpt|openai",
    r"youtube\s*(premium|music)",
    r"hbo\s*max",
    r"paramount",
    r"peacock",
    r"crunchyroll",
    r"notion",
    r"figma",
    r"canva",
    r"grammarly",
    r"nordvpn|expressvpn|surfshark",
    r"1password|lastpass|bitwarden",
    r"audible",
    r"kindle\s*unlimited",
    r"linkedin\s*premium",
    r"duolingo",
    r"headspace|calm",
    r"peloton",
    r"gym|fitness",
    r"insurance",
    r"internet|broadband|wifi",
    r"phone\s*(plan|bill)",
    r"electricity|power\s*bill",
    r"water\s*bill",
    r"gas\s*bill",
    r"rent",
]

# Cadence detection thresholds (in days)
CADENCE_RANGES = {
    "WEEKLY": (5, 9),
    "BIWEEKLY": (12, 17),
    "MONTHLY": (25, 35),
    "QUARTERLY": (80, 100),
    "YEARLY": (350, 380),
}


def normalize_merchant_name(name: str) -> str:
    """Normalize merchant name for comparison.

    Strips common prefixes/suffixes, lowercases, and removes extra whitespace.
    """
    if not name:
        return ""
    normalized = name.lower().strip()
    # Remove common payment prefixes
    for prefix in ["payment to ", "recurring payment ", "autopay ", "sub ", "subscription "]:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    # Remove date-like suffixes (e.g., "Netflix Jan 2024")
    normalized = re.sub(
        r"\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*\d{0,4}$",
        "",
        normalized,
    )
    # Remove trailing reference numbers
    normalized = re.sub(r"\s*#\d+$", "", normalized)
    normalized = re.sub(r"\s*ref\s*\d+$", "", normalized)
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _detect_cadence(dates: list[date]) -> tuple[str, float]:
    """Detect the most likely cadence from a sorted list of dates.

    Returns (cadence_name, regularity_score).
    Regularity score is 0.0-1.0 indicating how consistent the intervals are.
    """
    if len(dates) < 2:
        return "MONTHLY", 0.0

    sorted_dates = sorted(dates)
    intervals = [
        (sorted_dates[i + 1] - sorted_dates[i]).days
        for i in range(len(sorted_dates) - 1)
    ]

    avg_interval = sum(intervals) / len(intervals)

    # Find best matching cadence
    best_cadence = "MONTHLY"
    best_score = 0.0

    for cadence, (lo, hi) in CADENCE_RANGES.items():
        if lo <= avg_interval <= hi:
            # Calculate regularity: how close each interval is to the expected
            expected = (lo + hi) / 2
            deviations = [abs(iv - expected) / expected for iv in intervals]
            regularity = max(0.0, 1.0 - (sum(deviations) / len(deviations)))
            if regularity > best_score:
                best_score = regularity
                best_cadence = cadence

    return best_cadence, best_score


def _amount_consistency(amounts: list[Decimal]) -> float:
    """Score how consistent the amounts are (0.0-1.0).

    Returns 1.0 if all amounts are identical, lower for more variation.
    """
    if not amounts or len(amounts) < 2:
        return 1.0
    avg = sum(float(a) for a in amounts) / len(amounts)
    if avg == 0:
        return 0.0
    deviations = [abs(float(a) - avg) / avg for a in amounts]
    consistency = max(0.0, 1.0 - (sum(deviations) / len(deviations)))
    return consistency


def _is_known_service(name: str) -> bool:
    """Check if the merchant name matches a known subscription service."""
    lower = name.lower()
    for pattern in KNOWN_SERVICES:
        if re.search(pattern, lower):
            return True
    return False


def _compute_confidence(
    occurrence_count: int,
    amount_consistency: float,
    interval_regularity: float,
    is_known: bool,
) -> float:
    """Compute overall confidence score for a detected subscription.

    Weighted average of:
        - Occurrence factor (more charges = higher confidence)
        - Amount consistency (same amount each time = higher)
        - Interval regularity (consistent spacing = higher)
        - Known service bonus

    Returns a score between 0.0 and 1.0.
    """
    # Occurrence factor: logarithmic growth, caps at ~1.0 around 12 occurrences
    import math

    occ_factor = min(1.0, math.log2(max(1, occurrence_count)) / 3.5)

    weights = {
        "occurrence": 0.25,
        "amount": 0.30,
        "interval": 0.30,
        "known": 0.15,
    }

    score = (
        weights["occurrence"] * occ_factor
        + weights["amount"] * amount_consistency
        + weights["interval"] * interval_regularity
        + weights["known"] * (1.0 if is_known else 0.0)
    )
    return round(min(1.0, max(0.0, score)), 4)


def _estimate_next_date(last_date: date, cadence: str) -> date:
    """Estimate the next expected charge date based on cadence."""
    cadence_days = {
        "WEEKLY": 7,
        "BIWEEKLY": 14,
        "MONTHLY": 30,
        "QUARTERLY": 90,
        "YEARLY": 365,
    }
    days = cadence_days.get(cadence, 30)
    return last_date + timedelta(days=days)


def detect_subscriptions_for_user(user_id: int) -> list[dict]:
    """Scan all expenses for a user and detect subscription patterns.

    Groups expenses by normalized merchant name, analyzes patterns,
    and creates/updates DetectedSubscription records.

    Returns list of detected subscription dicts.
    """
    # Fetch all expenses for the user, ordered by date
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=user_id)
        .order_by(Expense.spent_at.asc())
        .all()
    )

    if not expenses:
        return []

    # Group by normalized merchant name
    groups: dict[str, list[Expense]] = defaultdict(list)
    for exp in expenses:
        name = normalize_merchant_name(exp.notes or "")
        if name:
            groups[name].append(exp)

    detected = []

    for normalized_name, exps in groups.items():
        # Need at least 2 charges to detect a pattern
        if len(exps) < 2:
            continue

        dates = [e.spent_at for e in exps]
        amounts = [e.amount for e in exps]

        cadence, interval_reg = _detect_cadence(dates)
        amt_consistency = _amount_consistency(amounts)
        is_known = _is_known_service(normalized_name)

        confidence = _compute_confidence(
            occurrence_count=len(exps),
            amount_consistency=amt_consistency,
            interval_regularity=interval_reg,
            is_known=is_known,
        )

        # Only consider subscriptions with reasonable confidence
        if confidence < 0.3 and not is_known:
            continue

        avg_amount = Decimal(str(round(sum(float(a) for a in amounts) / len(amounts), 2)))
        first_seen = min(dates)
        last_seen = max(dates)
        next_expected = _estimate_next_date(last_seen, cadence)
        merchant_name = exps[0].notes or normalized_name

        # Check for existing record
        existing = (
            db.session.query(DetectedSubscription)
            .filter_by(
                user_id=user_id,
                normalized_name=normalized_name,
                cadence=cadence,
            )
            .first()
        )

        if existing:
            # Update existing record
            existing.amount = avg_amount
            existing.last_seen = last_seen
            existing.next_expected = next_expected
            existing.occurrence_count = len(exps)
            existing.confidence = confidence
            existing.is_active = True
            existing.updated_at = date.today()
            sub = existing
        else:
            sub = DetectedSubscription(
                user_id=user_id,
                merchant_name=merchant_name,
                normalized_name=normalized_name,
                amount=avg_amount,
                currency=exps[0].currency,
                cadence=cadence,
                confidence=confidence,
                first_seen=first_seen,
                last_seen=last_seen,
                next_expected=next_expected,
                occurrence_count=len(exps),
                status="detected",
                category_id=exps[0].category_id,
                is_active=True,
            )
            db.session.add(sub)

        detected.append(sub)

    db.session.commit()

    logger.info(
        "Detected %d subscriptions for user %d", len(detected), user_id
    )
    return [_sub_to_dict(s) for s in detected]


def get_subscriptions(user_id: int, active_only: bool = True) -> list[dict]:
    """Get all detected subscriptions for a user."""
    q = db.session.query(DetectedSubscription).filter_by(user_id=user_id)
    if active_only:
        q = q.filter_by(is_active=True)
    subs = q.order_by(DetectedSubscription.confidence.desc()).all()
    return [_sub_to_dict(s) for s in subs]


def get_subscription_by_id(user_id: int, sub_id: int) -> DetectedSubscription | None:
    """Get a single detected subscription by ID."""
    return (
        db.session.query(DetectedSubscription)
        .filter_by(id=sub_id, user_id=user_id)
        .first()
    )


def update_subscription_status(
    user_id: int, sub_id: int, status: str
) -> dict | None:
    """Update subscription status (confirmed, dismissed, detected)."""
    valid_statuses = {"detected", "confirmed", "dismissed"}
    if status not in valid_statuses:
        return None

    sub = get_subscription_by_id(user_id, sub_id)
    if not sub:
        return None

    sub.status = status
    if status == "dismissed":
        sub.is_active = False
    elif status == "confirmed":
        sub.is_active = True
    sub.updated_at = date.today()
    db.session.commit()

    logger.info(
        "Updated subscription %d status to %s for user %d",
        sub_id, status, user_id,
    )
    return _sub_to_dict(sub)


def get_monthly_subscription_cost(user_id: int) -> dict:
    """Calculate the total monthly subscription cost for a user."""
    subs = (
        db.session.query(DetectedSubscription)
        .filter_by(user_id=user_id, is_active=True)
        .filter(DetectedSubscription.status.in_(["detected", "confirmed"]))
        .all()
    )

    monthly_total = Decimal("0.00")
    yearly_total = Decimal("0.00")

    cadence_multiplier = {
        "WEEKLY": Decimal("4.33"),
        "BIWEEKLY": Decimal("2.17"),
        "MONTHLY": Decimal("1.00"),
        "QUARTERLY": Decimal("0.33"),
        "YEARLY": Decimal("0.083"),
    }

    details = []
    for sub in subs:
        multiplier = cadence_multiplier.get(sub.cadence, Decimal("1.00"))
        monthly = sub.amount * multiplier
        monthly_total += monthly
        yearly_total += monthly * 12
        details.append({
            "id": sub.id,
            "name": sub.merchant_name,
            "amount": float(sub.amount),
            "cadence": sub.cadence,
            "monthly_equivalent": float(round(monthly, 2)),
            "confidence": float(sub.confidence),
        })

    return {
        "monthly_total": float(round(monthly_total, 2)),
        "yearly_total": float(round(yearly_total, 2)),
        "subscription_count": len(subs),
        "subscriptions": details,
    }


def _sub_to_dict(sub: DetectedSubscription) -> dict:
    """Convert a DetectedSubscription to a dict."""
    return {
        "id": sub.id,
        "merchant_name": sub.merchant_name,
        "normalized_name": sub.normalized_name,
        "amount": float(sub.amount),
        "currency": sub.currency,
        "cadence": sub.cadence,
        "confidence": float(sub.confidence),
        "first_seen": sub.first_seen.isoformat() if sub.first_seen else None,
        "last_seen": sub.last_seen.isoformat() if sub.last_seen else None,
        "next_expected": sub.next_expected.isoformat() if sub.next_expected else None,
        "occurrence_count": sub.occurrence_count,
        "status": sub.status,
        "linked_recurring_id": sub.linked_recurring_id,
        "category_id": sub.category_id,
        "is_active": sub.is_active,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
    }
