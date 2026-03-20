"""Tests for Event-Driven Financial Activity System."""
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime

from app.services.event_system import (
    FinancialEvent,
    EventType,
    subscribe,
    unsubscribe,
    emit,
    emit_expense_added,
    emit_bill_paid,
    emit_budget_exceeded,
    emit_anomaly_detected,
    _handlers,
)


def _make_mock_db():
    mock_session = MagicMock()
    mock_session.execute.return_value.lastrowid = 42
    mock_session.execute.return_value.fetchall.return_value = []
    return mock_session


# ──────────────────────────────────────────────
# Event creation
# ──────────────────────────────────────────────

def test_event_has_timestamp():
    event = FinancialEvent(
        event_type=EventType.EXPENSE_ADDED,
        user_id=1,
        payload={"amount": 50.0}
    )
    assert event.occurred_at.endswith("Z")


def test_event_type_values():
    assert EventType.EXPENSE_ADDED == "expense_added"
    assert EventType.BILL_PAID == "bill_paid"
    assert EventType.BUDGET_EXCEEDED == "budget_exceeded"
    assert EventType.ANOMALY_DETECTED == "anomaly_detected"


# ──────────────────────────────────────────────
# Subscribe / unsubscribe
# ──────────────────────────────────────────────

def test_subscribe_registers_handler():
    received = []
    def handler(e): received.append(e)

    with patch("app.services.event_system.db") as mock_db:
        mock_db.session = _make_mock_db()
        mock_db.text = MagicMock(return_value="")
        subscribe("test_event", handler)
        assert handler in _handlers.get("test_event", [])
        unsubscribe("test_event", handler)


def test_unsubscribe_removes_handler():
    received = []
    def handler(e): received.append(e)

    subscribe("remove_test", handler)
    unsubscribe("remove_test", handler)
    assert handler not in _handlers.get("remove_test", [])


# ──────────────────────────────────────────────
# Emit
# ──────────────────────────────────────────────

def test_emit_calls_handler():
    received = []
    def handler(e): received.append(e.event_type)

    subscribe(EventType.BILL_PAID, handler)
    try:
        with patch("app.services.event_system.db") as mock_db:
            mock_db.session = _make_mock_db()
            mock_db.text = MagicMock(return_value="")
            event = FinancialEvent(
                event_type=EventType.BILL_PAID,
                user_id=1,
                payload={"bill_id": 5, "amount": 100.0}
            )
            emit(event)
        assert EventType.BILL_PAID in received
    finally:
        unsubscribe(EventType.BILL_PAID, handler)


def test_emit_handler_exception_doesnt_stop_chain():
    called = []
    def bad_handler(e): raise ValueError("boom")
    def good_handler(e): called.append(1)

    subscribe("chain_test", bad_handler)
    subscribe("chain_test", good_handler)
    try:
        with patch("app.services.event_system.db") as mock_db:
            mock_db.session = _make_mock_db()
            mock_db.text = MagicMock(return_value="")
            event = FinancialEvent(event_type="chain_test", user_id=1, payload={})
            emit(event)
        assert len(called) == 1  # good_handler was still called
    finally:
        unsubscribe("chain_test", bad_handler)
        unsubscribe("chain_test", good_handler)


# ──────────────────────────────────────────────
# Convenience emitters
# ──────────────────────────────────────────────

def test_emit_expense_added():
    with patch("app.services.event_system.db") as mock_db:
        mock_db.session = _make_mock_db()
        mock_db.text = MagicMock(return_value="")
        event_id = emit_expense_added(1, 10, 25.0, "Coffee")
        assert isinstance(event_id, int)


def test_emit_bill_paid():
    with patch("app.services.event_system.db") as mock_db:
        mock_db.session = _make_mock_db()
        mock_db.text = MagicMock(return_value="")
        event_id = emit_bill_paid(1, 3, 150.0)
        assert isinstance(event_id, int)


def test_emit_budget_exceeded():
    with patch("app.services.event_system.db") as mock_db:
        mock_db.session = _make_mock_db()
        mock_db.text = MagicMock(return_value="")
        event_id = emit_budget_exceeded(1, "Food", 300.0, 420.0)
        assert isinstance(event_id, int)


def test_emit_anomaly_detected():
    with patch("app.services.event_system.db") as mock_db:
        mock_db.session = _make_mock_db()
        mock_db.text = MagicMock(return_value="")
        event_id = emit_anomaly_detected(1, 99, "Amount 5x normal", 1500.0)
        assert isinstance(event_id, int)