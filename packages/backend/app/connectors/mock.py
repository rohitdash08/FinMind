"""
Mock Connector for testing and development.

This connector provides a mock implementation that generates
sample transaction data for testing the connector architecture.
"""

import logging
from datetime import date, timedelta
from typing import Any
from random import random, choice, uniform

from app.connectors import (
    BaseConnector,
    ConnectorType,
    Transaction,
    Account,
    ConnectorRegistry,
)

logger = logging.getLogger("finmind.connectors.mock")


# Sample data for generating mock transactions
MOCK_ACCOUNTS = [
    Account(
        account_id="mock_checking_001",
        account_name="Mock Checking Account",
        account_type="CHECKING",
        balance=5432.10,
        currency="USD",
    ),
    Account(
        account_id="mock_savings_001",
        account_name="Mock Savings Account",
        account_type="SAVINGS",
        balance=12500.00,
        currency="USD",
    ),
    Account(
        account_id="mock_credit_001",
        account_name="Mock Credit Card",
        account_type="CREDIT",
        balance=-1250.75,
        currency="USD",
    ),
]

MOCK_MERCHANTS = [
    "Amazon",
    "Walmart",
    "Target",
    "Starbucks",
    "Netflix",
    "Spotify",
    "Uber",
    "Lyft",
    "Whole Foods",
    "Costco",
    "Shell Gas Station",
    "CVS Pharmacy",
    "Apple Store",
    "Google Play",
    "Electric Company",
    "Water Utility",
    "Internet Provider",
    "Phone Bill",
    "Restaurant",
    "Gym Membership",
]

MOCK_INCOME_SOURCES = [
    "Payroll Deposit",
    "Direct Deposit - Employer",
    "Transfer from Savings",
    "Refund - Online Purchase",
    "Interest Payment",
]


@ConnectorRegistry.register(ConnectorType.MOCK)
class MockConnector(BaseConnector):
    """
    Mock connector for testing and development purposes.

    This connector generates realistic-looking mock transactions
    without requiring actual bank API credentials.
    """

    def __init__(
        self,
        api_key: str | None = None,
        secret: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize the mock connector.

        Args:
            api_key: Optional API key (not used in mock)
            secret: Optional secret (not used in mock)
            **kwargs: Additional configuration options
        """
        self._api_key = api_key
        self._secret = secret
        self._seed = kwargs.get("seed", None)
        self._config = kwargs

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.MOCK

    def import_transactions(
        self,
        user_id: int,
        account_id: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Transaction]:
        """
        Generate mock transactions.

        Args:
            user_id: The user ID (used for logging)
            account_id: Optional account filter
            from_date: Optional start date (defaults to 30 days ago)
            to_date: Optional end date (defaults to today)

        Returns:
            List of mock Transaction objects
        """
        # Default date range: last 30 days
        if to_date is None:
            to_date = date.today()
        if from_date is None:
            from_date = to_date - timedelta(days=30)

        logger.info(
            "Mock import for user=%s account=%s from=%s to=%s",
            user_id,
            account_id,
            from_date,
            to_date,
        )

        transactions: list[Transaction] = []
        current_date = from_date

        # Generate 1-3 transactions per day
        while current_date <= to_date:
            num_transactions = choice([1, 1, 1, 2, 2, 3])

            for _ in range(num_transactions):
                # Determine if this is income or expense
                is_income = random() < 0.15  # 15% chance of income

                if is_income:
                    description = choice(MOCK_INCOME_SOURCES)
                    amount = uniform(500, 5000)
                    expense_type = "INCOME"
                else:
                    description = choice(MOCK_MERCHANTS)
                    amount = uniform(5, 200)
                    expense_type = "EXPENSE"

                transactions.append(
                    Transaction(
                        date=current_date,
                        amount=round(amount, 2),
                        description=description,
                        category_id=None,
                        expense_type=expense_type,
                        currency="USD",
                    )
                )

            current_date += timedelta(days=1)

        # Sort by date descending
        transactions.sort(key=lambda t: t.date, reverse=True)

        logger.info(
            "Generated %d mock transactions for user=%s",
            len(transactions),
            user_id,
        )

        return transactions

    def refresh(self, user_id: int) -> dict[str, Any]:
        """
        Simulate a refresh operation.

        Args:
            user_id: The user ID to refresh data for

        Returns:
            Dictionary with refresh status
        """
        logger.info("Mock refresh for user=%s", user_id)

        # Generate a few new transactions (simulating recent activity)
        new_transactions = self.import_transactions(
            user_id=user_id,
            from_date=date.today() - timedelta(days=3),
            to_date=date.today(),
        )

        return {
            "status": "success",
            "new_transactions": len(new_transactions),
            "accounts": len(self.get_accounts(user_id)),
            "last_refresh": date.today().isoformat(),
        }

    def get_accounts(self, user_id: int) -> list[Account]:
        """
        Get mock accounts.

        Args:
            user_id: The user ID (used for logging)

        Returns:
            List of mock Account objects
        """
        logger.info("Get accounts for user=%s", user_id)
        return MOCK_ACCOUNTS.copy()

    def validate_credentials(self) -> bool:
        """
        Mock credentials are always valid.

        Returns:
            True
        """
        return True
