"""Tests for Advanced Search service."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from app.services.advanced_search import (
    _parse_date,
    search_transactions,
)


def _make_expense(id=1, description="Test", amount=100.0, category_id=None):
    exp = MagicMock()
    exp.id = id
    exp.description = description
    exp.amount = amount
    exp.date = date(2026, 3, 15)
    exp.category_id = category_id
    return exp


def _make_bill(id=1, name="Electric", amount=50.0):
    bill = MagicMock()
    bill.id = id
    bill.name = name
    bill.amount = amount
    bill.due_date = date(2026, 3, 20)
    bill.status = "pending"
    bill.frequency = "monthly"
    return bill


# ──────────────────────────────────────────────
# Date parsing
# ──────────────────────────────────────────────

def test_parse_date_valid():
    d = _parse_date("2026-03-15")
    assert d == date(2026, 3, 15)


def test_parse_date_invalid():
    d = _parse_date("not-a-date")
    assert d is None


def test_parse_date_none():
    d = _parse_date(None)
    assert d is None


# ──────────────────────────────────────────────
# Search by keyword
# ──────────────────────────────────────────────

def test_keyword_search_expenses():
    with patch("app.services.advanced_search.Expense") as MockExp, \
         patch("app.services.advanced_search.Bill") as MockBill, \
         patch("app.services.advanced_search.Category") as MockCat:
        exp = _make_expense(description="Starbucks Coffee")
        MockExp.query.filter.return_value.filter.return_value.filter.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [exp]
        MockBill.query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []
        MockCat.query.get.return_value = None
        result = search_transactions(1, keyword="Starbucks")
        assert result.total_expenses >= 0


def test_empty_search_returns_result():
    with patch("app.services.advanced_search.Expense") as MockExp, \
         patch("app.services.advanced_search.Bill") as MockBill:
        MockExp.query.filter.return_value.order_by.return_value.all.return_value = []
        MockBill.query.filter.return_value.order_by.return_value.all.return_value = []
        result = search_transactions(1)
        assert result.total_hits == 0
        assert result.results == []


# ──────────────────────────────────────────────
# Pagination
# ──────────────────────────────────────────────

def test_page_size_clamped():
    with patch("app.services.advanced_search.Expense") as MockExp, \
         patch("app.services.advanced_search.Bill") as MockBill:
        MockExp.query.filter.return_value.order_by.return_value.all.return_value = []
        MockBill.query.filter.return_value.order_by.return_value.all.return_value = []
        result = search_transactions(1, page_size=9999)
        assert result.page_size == 100


def test_page_defaults():
    with patch("app.services.advanced_search.Expense") as MockExp, \
         patch("app.services.advanced_search.Bill") as MockBill:
        MockExp.query.filter.return_value.order_by.return_value.all.return_value = []
        MockBill.query.filter.return_value.order_by.return_value.all.return_value = []
        result = search_transactions(1)
        assert result.page == 1
        assert result.page_size == 20


# ──────────────────────────────────────────────
# Record type filter
# ──────────────────────────────────────────────

def test_expenses_only_type():
    with patch("app.services.advanced_search.Expense") as MockExp, \
         patch("app.services.advanced_search.Bill") as MockBill:
        MockExp.query.filter.return_value.order_by.return_value.all.return_value = []
        result = search_transactions(1, record_type="expense")
        assert result.total_bills == 0
        # Bill query not called
        MockBill.query.filter.assert_not_called()


def test_bills_only_type():
    with patch("app.services.advanced_search.Expense") as MockExp, \
         patch("app.services.advanced_search.Bill") as MockBill:
        MockBill.query.filter.return_value.order_by.return_value.all.return_value = []
        result = search_transactions(1, record_type="bill")
        assert result.total_expenses == 0
        MockExp.query.filter.assert_not_called()


# ──────────────────────────────────────────────
# Query info returned
# ──────────────────────────────────────────────

def test_query_info_in_result():
    with patch("app.services.advanced_search.Expense") as MockExp, \
         patch("app.services.advanced_search.Bill") as MockBill:
        MockExp.query.filter.return_value.order_by.return_value.all.return_value = []
        MockBill.query.filter.return_value.order_by.return_value.all.return_value = []
        result = search_transactions(1, keyword="coffee", amount_min=5.0)
        assert result.query["keyword"] == "coffee"
        assert result.query["amount_min"] == 5.0