"""
Automatic subscription detection from recurring expense patterns.

Identifies subscription services automatically by analyzing:
1. Expense recurrence patterns (regular cadence)
2. Merchant/payee name patterns (known subscription services)
3. Fixed-amount charge patterns (subscriptions rarely vary)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
import re


# ─── Known subscription patterns ─────────────────────────────────────────────

# Maps normalized merchant keywords to subscription service name
KNOWN_SUBSCRIPTIONS: dict[str, str] = {
    # Streaming
    "netflix": "Netflix",
    "spotify": "Spotify",
    "youtube premium": "YouTube Premium",
    "youtube music": "YouTube Music",
    "apple music": "Apple Music",
    "apple tv": "Apple TV+",
    "apple icloud": "Apple iCloud",
    "apple one": "Apple One",
    "hulu": "Hulu",
    "disney": "Disney+",
    "amazon prime": "Amazon Prime",
    "amazon music": "Amazon Music",
    "hbo": "HBO Max",
    "paramount": "Paramount+",
    "peacock": "Peacock",
    "crunchyroll": "Crunchyroll",
    "twitch": "Twitch",
    # Software
    "adobe": "Adobe",
    "microsoft 365": "Microsoft 365",
    "office 365": "Microsoft 365",
    "google one": "Google One",
    "google workspace": "Google Workspace",
    "dropbox": "Dropbox",
    "github": "GitHub",
    "notion": "Notion",
    "slack": "Slack",
    "zoom": "Zoom",
    "1password": "1Password",
    "nordvpn": "NordVPN",
    "expressvpn": "ExpressVPN",
    "grammarly": "Grammarly",
    "canva": "Canva",
    "figma": "Figma",
    "chatgpt": "ChatGPT Plus",
    "openai": "OpenAI",
    "anthropic": "Anthropic Claude",
    "midjourney": "Midjourney",
    # Gaming
    "playstation plus": "PlayStation Plus",
    "xbox game pass": "Xbox Game Pass",
    "nintendo online": "Nintendo Online",
    "steam": "Steam",
    # Other
    "duolingo": "Duolingo",
    "calm": "Calm",
    "headspace": "Headspace",
    "medium": "Medium",
    "substack": "Substack",
}


@dataclass
class ExpenseEntry:
    """Minimal expense record for subscription detection."""
    id: int
    amount: Decimal
    date: date
    description: str     # merchant/payee name
    notes: str = ""


@dataclass
class DetectedSubscription:
    """A detected subscription service."""
    service_name: str
    confidence: float           # 0.0 - 1.0
    detection_source: str       # "name_match" | "pattern_analysis" | "both"
    estimated_monthly_cost: Decimal
    charge_count: int
    first_seen: date
    last_seen: date
    sample_expense_id: int
    average_amount: Decimal
    cadence_hint: str           # MONTHLY | YEARLY | WEEKLY | UNKNOWN

    def to_dict(self) -> dict:
        return {
            "service_name": self.service_name,
            "confidence": round(self.confidence, 3),
            "detection_source": self.detection_source,
            "estimated_monthly_cost": str(self.estimated_monthly_cost.quantize(Decimal("0.01"))),
            "charge_count": self.charge_count,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "sample_expense_id": self.sample_expense_id,
            "average_amount": str(self.average_amount.quantize(Decimal("0.01"))),
            "cadence_hint": self.cadence_hint,
        }


# ─── Detection logic ──────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase and strip common transaction noise."""
    text = text.lower()
    text = re.sub(r'\*+', ' ', text)           # asterisks used by some processors
    text = re.sub(r'\d{4,}', '', text)         # strip long numbers (last4, merchant IDs)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)   # keep alphanumeric
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def match_known_service(description: str, notes: str = "") -> str | None:
    """
    Return canonical service name if any known keyword matches description or notes.
    Returns None if no match found.
    """
    text = _normalize(f"{description} {notes}")
    # Sort by length descending to prefer longer/more specific matches
    for keyword, name in sorted(KNOWN_SUBSCRIPTIONS.items(), key=lambda kv: -len(kv[0])):
        if keyword in text:
            return name
    return None


def _cadence_from_charges(sorted_dates: list[date]) -> str:
    """Infer billing cadence from sorted charge dates."""
    if len(sorted_dates) < 2:
        return "UNKNOWN"

    gaps = [(sorted_dates[i] - sorted_dates[i - 1]).days
            for i in range(1, len(sorted_dates))]
    avg_gap = sum(gaps) / len(gaps)

    if avg_gap < 10:
        return "WEEKLY"
    if avg_gap < 50:
        return "MONTHLY"
    if avg_gap < 200:
        return "QUARTERLY"
    return "YEARLY"


def _monthly_cost(amount: Decimal, cadence: str) -> Decimal:
    """Convert charge amount to estimated monthly equivalent."""
    multipliers = {
        "WEEKLY": Decimal("4.33"),
        "MONTHLY": Decimal("1"),
        "QUARTERLY": Decimal("0.333"),
        "YEARLY": Decimal("0.0833"),
    }
    return (amount * multipliers.get(cadence, Decimal("1"))).quantize(Decimal("0.01"))


def _amount_is_consistent(amounts: list[Decimal], tolerance: Decimal = Decimal("0.05")) -> bool:
    """Return True if all amounts are within ±tolerance of the mean."""
    if not amounts:
        return False
    mean = sum(amounts) / len(amounts)
    if mean == 0:
        return False
    return all(abs(a - mean) / mean <= tolerance for a in amounts)


def detect_from_expenses(
    expenses: list[ExpenseEntry],
    min_occurrences: int = 2,
    lookback_days: int = 365,
) -> list[DetectedSubscription]:
    """
    Analyze expense list and detect likely subscription charges.

    Strategy:
    1. Filter to lookback window.
    2. Group by normalized description.
    3. For each group:
       a. Name match against known services (+0.5 confidence).
       b. Regular cadence detection (+0.3 confidence).
       c. Consistent amounts (+0.2 confidence).
    4. Return groups with confidence >= 0.5.

    Returns list of DetectedSubscription sorted by monthly_cost desc.
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    recent = [e for e in expenses if e.date >= cutoff]

    # Group by normalized description
    groups: dict[str, list[ExpenseEntry]] = {}
    for exp in recent:
        key = _normalize(exp.description)
        if not key:
            continue
        groups.setdefault(key, []).append(exp)

    subscriptions: list[DetectedSubscription] = []

    for norm_desc, group in groups.items():
        if len(group) < min_occurrences:
            continue

        sorted_group = sorted(group, key=lambda e: e.date)
        amounts = [e.amount for e in sorted_group]
        dates = [e.date for e in sorted_group]

        # Confidence components
        confidence = 0.0
        detection_sources = []

        # Name matching
        sample_exp = sorted_group[0]
        service_name = match_known_service(sample_exp.description, sample_exp.notes)
        if service_name:
            confidence += 0.5
            detection_sources.append("name_match")
        else:
            service_name = norm_desc.title()

        # Cadence analysis
        cadence = _cadence_from_charges(dates)
        if cadence in ("MONTHLY", "YEARLY", "QUARTERLY"):
            confidence += 0.3
            detection_sources.append("pattern_analysis")

        # Amount consistency
        if _amount_is_consistent(amounts):
            confidence += 0.2

        if confidence < 0.4:
            continue

        avg_amount = sum(amounts) / len(amounts)
        monthly_cost = _monthly_cost(avg_amount, cadence)

        subscriptions.append(DetectedSubscription(
            service_name=service_name,
            confidence=min(confidence, 1.0),
            detection_source=" + ".join(detection_sources) if detection_sources else "pattern_analysis",
            estimated_monthly_cost=monthly_cost,
            charge_count=len(group),
            first_seen=dates[0],
            last_seen=dates[-1],
            sample_expense_id=sample_exp.id,
            average_amount=avg_amount.quantize(Decimal("0.01")),
            cadence_hint=cadence,
        ))

    # Sort by monthly cost desc
    subscriptions.sort(key=lambda s: s.estimated_monthly_cost, reverse=True)
    return subscriptions


def detection_summary(subscriptions: list[DetectedSubscription]) -> dict:
    """Summarize detected subscriptions."""
    total_monthly = sum((s.estimated_monthly_cost for s in subscriptions), Decimal('0'))
    high_confidence = [s for s in subscriptions if s.confidence >= 0.7]
    return {
        "total_detected": len(subscriptions),
        "high_confidence_count": len(high_confidence),
        "estimated_total_monthly_spend": str(total_monthly.quantize(Decimal("0.01"))),
        "estimated_total_annual_spend": str((total_monthly * 12).quantize(Decimal("0.01"))),
    }