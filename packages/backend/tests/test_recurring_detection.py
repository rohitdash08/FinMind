from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.recurring_detection import detect_recurring_expenses


def _expense(
    expense_id,
    description,
    spent_at,
    *,
    amount="15.99",
    currency="USD",
    expense_type="EXPENSE",
    category_id=1,
    source_recurring_id=None,
):
    return SimpleNamespace(
        id=expense_id,
        amount=Decimal(amount),
        currency=currency,
        expense_type=expense_type,
        category_id=category_id,
        notes=description,
        spent_at=date.fromisoformat(spent_at),
        source_recurring_id=source_recurring_id,
    )


def test_detect_recurring_expenses_finds_monthly_subscription_noise():
    expenses = [
        _expense(1, "Netflix Streaming 483920", "2026-01-05"),
        _expense(2, "Netflix Streaming 582011", "2026-02-05"),
        _expense(3, "Netflix Streaming 671102", "2026-03-06"),
        _expense(4, "Groceries", "2026-01-05"),
        _expense(5, "Groceries", "2026-01-13"),
        _expense(6, "Groceries", "2026-01-28"),
    ]

    candidates = detect_recurring_expenses(expenses)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.description == "Netflix Streaming 483920"
    assert candidate.amount == Decimal("15.99")
    assert candidate.currency == "USD"
    assert candidate.category_id == 1
    assert candidate.cadence == "MONTHLY"
    assert candidate.confidence == "HIGH"
    assert candidate.start_date == date(2026, 1, 5)
    assert candidate.last_seen_date == date(2026, 3, 6)
    assert candidate.next_expected_date == date(2026, 4, 6)
    assert candidate.matching_expense_ids == [1, 2, 3]


def test_detect_recurring_expenses_skips_generated_rows_and_income():
    expenses = [
        _expense(1, "Cloud Storage", "2026-01-10", source_recurring_id=7),
        _expense(2, "Cloud Storage", "2026-02-10", source_recurring_id=7),
        _expense(3, "Cloud Storage", "2026-03-10", source_recurring_id=7),
        _expense(4, "Payroll Deposit", "2026-01-15", expense_type="INCOME"),
        _expense(5, "Payroll Deposit", "2026-02-15", expense_type="INCOME"),
        _expense(6, "Payroll Deposit", "2026-03-15", expense_type="INCOME"),
    ]

    assert detect_recurring_expenses(expenses) == []
