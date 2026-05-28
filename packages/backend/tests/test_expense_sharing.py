"""Tests for Expense Sharing."""

import pytest


class TestExpenseSharing:
    def test_create_group(self):
        from app.services.expense_sharing import ExpenseSharingService
        svc = ExpenseSharingService()
        g = svc.create_group("Weekend Trip", "user1")
        assert g["name"] == "Weekend Trip"
        assert "user1" in g["members"]

    def test_equal_split(self):
        from app.services.expense_sharing import ExpenseSharingService
        svc = ExpenseSharingService()
        result = svc.split_expense(
            payer_id="user1", total_amount=100, description="dinner",
            split_type="equal", participants=["user1", "user2", "user3"],
        )
        assert result["total_amount"] == 100
        assert all(v == pytest.approx(33.33, rel=0.1) for v in result["splits"].values())

    def test_custom_split(self):
        from app.services.expense_sharing import ExpenseSharingService
        svc = ExpenseSharingService()
        result = svc.split_expense(
            payer_id="user1", total_amount=100, description="hotel",
            split_type="custom", participants=["user1", "user2"],
            custom_splits={"user1": 60, "user2": 40},
        )
        assert result["splits"]["user1"] == 60
        assert result["splits"]["user2"] == 40

    def test_settlement(self):
        from app.services.expense_sharing import ExpenseSharingService
        svc = ExpenseSharingService()
        expense = svc.split_expense(
            payer_id="user1", total_amount=100, description="gas",
            split_type="equal", participants=["user1", "user2"],
        )
        result = svc.settle(expense["expense_id"], "user2", 50)
        assert result["expense"]["status"] == "settled"

    def test_balance(self):
        from app.services.expense_sharing import ExpenseSharingService
        svc = ExpenseSharingService()
        svc.split_expense("user1", 90, "lunch", "equal",
                          ["user1", "user2", "user3"])
        svc.split_expense("user2", 60, "coffee", "equal",
                          ["user1", "user2"])
        balance = svc.get_balance()
        assert balance["total_owed"] > 0
        assert len(balance["simplified_debts"]) > 0

    def test_debt_simplification(self):
        from app.services.expense_sharing import ExpenseSharingService
        svc = ExpenseSharingService()
        svc.split_expense("A", 60, "dinner", "equal", ["A", "B", "C"])
        svc.split_expense("B", 30, "movie", "equal", ["A", "B"])
        balance = svc.get_balance()
        # Should have fewer transactions than raw debts
        assert len(balance["simplified_debts"]) <= 3
