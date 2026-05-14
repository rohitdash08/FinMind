import calendar
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.models import Expense, RecurringCadence


@dataclass(frozen=True)
class RecurringCandidate:
    amount: Decimal
    currency: str
    expense_type: str
    category_id: int | None
    description: str
    cadence: str
    start_date: date
    last_seen_date: date
    next_expected_date: date
    occurrences: int
    confidence: str
    matching_expense_ids: list[int]


def detect_recurring_expenses(
    expenses: list[Expense],
    *,
    min_occurrences: int = 3,
) -> list[RecurringCandidate]:
    groups: dict[tuple, list[Expense]] = defaultdict(list)
    for expense in expenses:
        if expense.source_recurring_id is not None:
            continue
        if str(expense.expense_type).upper() == "INCOME":
            continue
        key = (
            _normalize_description(expense.notes or ""),
            Decimal(expense.amount).quantize(Decimal("0.01")),
            expense.currency,
            str(expense.expense_type).upper(),
            expense.category_id,
        )
        if not key[0]:
            continue
        groups[key].append(expense)

    candidates: list[RecurringCandidate] = []
    for (
        _normalized,
        amount,
        currency,
        expense_type,
        category_id,
    ), items in groups.items():
        if len(items) < min_occurrences:
            continue
        ordered = sorted(items, key=lambda item: item.spent_at)
        cadence, confidence = _infer_cadence([item.spent_at for item in ordered])
        if cadence is None:
            continue
        descriptions = [item.notes or "" for item in ordered]
        description = Counter(descriptions).most_common(1)[0][0]
        last_seen = ordered[-1].spent_at
        candidates.append(
            RecurringCandidate(
                amount=amount,
                currency=currency,
                expense_type=expense_type,
                category_id=category_id,
                description=description,
                cadence=cadence,
                start_date=ordered[0].spent_at,
                last_seen_date=last_seen,
                next_expected_date=_advance_date(last_seen, cadence),
                occurrences=len(ordered),
                confidence=confidence,
                matching_expense_ids=[item.id for item in ordered],
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            _confidence_rank(candidate.confidence),
            candidate.occurrences,
            candidate.last_seen_date,
        ),
        reverse=True,
    )


def recurring_candidate_to_dict(candidate: RecurringCandidate) -> dict:
    return {
        "amount": float(candidate.amount),
        "currency": candidate.currency,
        "expense_type": candidate.expense_type,
        "category_id": candidate.category_id,
        "description": candidate.description,
        "cadence": candidate.cadence,
        "start_date": candidate.start_date.isoformat(),
        "last_seen_date": candidate.last_seen_date.isoformat(),
        "next_expected_date": candidate.next_expected_date.isoformat(),
        "occurrences": candidate.occurrences,
        "confidence": candidate.confidence,
        "matching_expense_ids": candidate.matching_expense_ids,
    }


def _normalize_description(description: str) -> str:
    value = description.lower()
    value = re.sub(r"\b\d{2,}\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _infer_cadence(dates: list[date]) -> tuple[str | None, str | None]:
    unique_dates = sorted(set(dates))
    if len(unique_dates) < 2:
        return None, None
    deltas = [
        (right - left).days for left, right in zip(unique_dates, unique_dates[1:])
    ]
    checks = [
        (RecurringCadence.DAILY.value, _matches_fixed_delta(deltas, 1, tolerance=0)),
        (RecurringCadence.WEEKLY.value, _matches_fixed_delta(deltas, 7, tolerance=1)),
        (RecurringCadence.MONTHLY.value, _matches_monthly(unique_dates)),
        (RecurringCadence.YEARLY.value, _matches_yearly(unique_dates)),
    ]
    cadence, score = max(checks, key=lambda item: item[1])
    if score < 0.75:
        return None, None
    return cadence, "HIGH" if score == 1.0 else "MEDIUM"


def _matches_fixed_delta(deltas: list[int], expected: int, *, tolerance: int) -> float:
    if not deltas:
        return 0.0
    matches = sum(1 for delta in deltas if abs(delta - expected) <= tolerance)
    return matches / len(deltas)


def _matches_monthly(dates: list[date]) -> float:
    return _matches_calendar_cadence(dates, RecurringCadence.MONTHLY.value, tolerance=3)


def _matches_yearly(dates: list[date]) -> float:
    return _matches_calendar_cadence(dates, RecurringCadence.YEARLY.value, tolerance=7)


def _matches_calendar_cadence(
    dates: list[date],
    cadence: str,
    *,
    tolerance: int,
) -> float:
    if len(dates) < 2:
        return 0.0
    matches = 0
    for left, right in zip(dates, dates[1:]):
        expected = _advance_date(left, cadence)
        if abs((right - expected).days) <= tolerance:
            matches += 1
    return matches / (len(dates) - 1)


def _advance_date(at: date, cadence: str) -> date:
    if cadence == RecurringCadence.DAILY.value:
        return at + timedelta(days=1)
    if cadence == RecurringCadence.WEEKLY.value:
        return at + timedelta(days=7)
    if cadence == RecurringCadence.MONTHLY.value:
        year = at.year + (1 if at.month == 12 else 0)
        month = 1 if at.month == 12 else at.month + 1
        day = min(at.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    year = at.year + 1
    day = min(at.day, calendar.monthrange(year, at.month)[1])
    return date(year, at.month, day)


def _confidence_rank(confidence: str) -> int:
    return {"HIGH": 2, "MEDIUM": 1}.get(confidence, 0)
