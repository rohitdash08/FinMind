import unittest
from app import create_app
from app.models import FinancialAccount

class TestDashboard(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

        self.account1 = FinancialAccount(name="Account 1", balance=1000, user_id=1)
        self.account2 = FinancialAccount(name="Account 2", balance=2000, user_id=1)

    def test_multi_account_dashboard(self):
        response = self.client.get("/dashboard/1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account 1", response.data)
        self.assertIn(b"Account 2", response.data)
        self.assertIn(b"Balance: 1000", response.data)
        self.assertIn(b"Balance: 2000", response.data)

if __name__ == "__main__":
    unittest.main()