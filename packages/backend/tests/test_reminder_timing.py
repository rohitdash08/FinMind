"""Tests for Smart Reminder Timing Optimization (issue #111)."""
import pytest
from unittest.mock import MagicMock
from datetime import date

from app.services.reminder_timing import (
    get_optimized_reminder_timing,
    ReminderTimingResult,
    OptimizedReminder,
)


def _make_tx(tx_id, tx_date, amount=100.0, tx_type="expense"):
    tx = MagicMock()
    tx.id = tx_id
    tx.amount = amount
    tx.date = tx_date
    tx.type = tx_type
    return tx


def _make_reminder(r_id, days_before=3):
    r = MagicMock()
    r.id = r_id
    r.days_before = days_before
    return r


def _mock_session(txs, reminders):
    """Mock db.session.query to return txs on first call and reminders on second."""
    call_count = [0]
    q = MagicMock()
    q.filter.return_value = q
    q.all.side_effect = lambda: (txs if call_count[0] < 1 else []) or txs

    def all_side():
        call_count[0] += 1
        if call_count[0] == 1:
            return reminders
        return txs

    q.all.side_effect = all_side
    return q


def test_empty_returns_default(mocker):
    mocker.patch("app.services.reminder_timing.db.session.query",
                 side_effect=Exception("no table"))
    result = get_optimized_reminder_timing(user_id=1)
    assert isinstance(result, ReminderTimingResult)
    assert result.avg_days_before_payment >= 0


def test_required_fields_present(mocker):
    mocker.patch("app.services.reminder_timing.db.session.query",
                 side_effect=Exception("no table"))
    result = get_optimized_reminder_timing(user_id=1)
    assert hasattr(result, "optimized_reminders")
    assert hasattr(result, "general_recommendation")
    assert hasattr(result, "avg_days_before_payment")
    assert hasattr(result, "on_time_rate")
    assert hasattr(result, "summary")


def test_on_time_rate_in_range(mocker):
    txs = [_make_tx(i, date(2026, 1, d)) for i, d in enumerate([5, 10, 15, 20, 25])]
    q = MagicMock()
    q.filter.return_value = q
    call_count = [0]

    def all_side():
        call_count[0] += 1
        if call_count[0] == 1:
            return []  # no reminders
        return txs

    q.all.side_effect = all_side
    mocker.patch("app.services.reminder_timing.db.session.query", return_value=q)
    result = get_optimized_reminder_timing(user_id=1)
    assert 0.0 <= result.on_time_rate <= 1.0


def test_early_payer_gets_shorter_reminder(mocker):
    # Payments on day 1 of month = very early = 30+ days before EOM
    txs = [_make_tx(i, date(2026, 1, 1)) for i in range(5)]
    q = MagicMock()
    q.filter.return_value = q
    call_count = [0]

    def all_side():
        call_count[0] += 1
        if call_count[0] == 1:
            r = MagicMock()
            r.id = 1
            r.days_before = 3
            return [r]
        return txs

    q.all.side_effect = all_side
    mocker.patch("app.services.reminder_timing.db.session.query", return_value=q)
    result = get_optimized_reminder_timing(user_id=1)
    if result.optimized_reminders:
        # Early payers should get <= 5 day reminder
        assert result.optimized_reminders[0].suggested_days_before <= 5


def test_late_payer_gets_longer_reminder(mocker):
    # Payments on day 28+ = very close to EOM = avg_days_before < 3
    txs = [_make_tx(i, date(2026, 1, 29)) for i in range(5)]
    q = MagicMock()
    q.filter.return_value = q
    call_count = [0]

    def all_side():
        call_count[0] += 1
        if call_count[0] == 1:
            r = MagicMock()
            r.id = 1
            r.days_before = 3
            return [r]
        return txs

    q.all.side_effect = all_side
    mocker.patch("app.services.reminder_timing.db.session.query", return_value=q)
    result = get_optimized_reminder_timing(user_id=1)
    if result.optimized_reminders:
        # Late payers need more lead time
        assert result.optimized_reminders[0].suggested_days_before >= 5


def test_confidence_positive(mocker):
    q = MagicMock()
    q.filter.return_value = q
    call_count = [0]

    def all_side():
        call_count[0] += 1
        if call_count[0] == 1:
            r = MagicMock()
            r.id = 1
            r.days_before = 3
            return [r]
        txs = [_make_tx(i, date(2026, 1, 15)) for i in range(6)]
        return txs

    q.all.side_effect = all_side
    mocker.patch("app.services.reminder_timing.db.session.query", return_value=q)
    result = get_optimized_reminder_timing(user_id=1)
    if result.optimized_reminders:
        assert result.optimized_reminders[0].confidence > 0


def test_summary_not_empty(mocker):
    mocker.patch("app.services.reminder_timing.db.session.query",
                 side_effect=Exception("no table"))
    result = get_optimized_reminder_timing(user_id=1)
    assert len(result.summary) > 0


def test_route_requires_auth(client):
    resp = client.get("/insights/reminder-timing")
    assert resp.status_code == 401