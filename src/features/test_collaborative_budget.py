import unittest
from src.features.collaborative_budget import CollaborativeBudget

class TestCollaborativeBudget(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = CollaborativeBudget(budget_name='Vacation Fund', users=['Alice', 'Bob', 'Charlie'], total_amount=3000.0)

    def test_add_contribution(self) -> None:
        self.budget.add_contribution('Alice', 1000.0)
        self.assertEqual(self.budget.get_user_balance('Alice'), 1000.0)
        self.assertEqual(self.budget.get_remaining_budget(), 2000.0)

    def test_add_invalid_contribution(self) -> None:
        with self.assertRaises(ValueError):
            self.budget.add_contribution('Alice', -500.0)

    def test_settle_budget(self) -> None:
        self.budget.add_contribution('Alice', 1000.0)
        self.budget.add_contribution('Bob', 1000.0)
        self.budget.add_contribution('Charlie', 1000.0)
        balance = self.budget.settle_budget()
        self.assertEqual(balance, {'Alice': 0.0, 'Bob': 0.0, 'Charlie': 0.0})

    def test_get_user_balance_for_non_participant(self) -> None:
        with self.assertRaises(ValueError):
            self.budget.get_user_balance('Dave')

    def test_get_remaining_budget_for_under_contribution(self) -> None:
        self.budget.add_contribution('Alice', 500.0)
        self.assertEqual(self.budget.get_remaining_budget(), 2500.0)

if __name__ == '__main__':
    unittest.main()