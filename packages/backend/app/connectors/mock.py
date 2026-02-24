"""Mock bank connector for local development and CI tests.

Returns realistic Indian bank transaction data (INR, UPI, NEFT, IMPS)
without any external dependencies.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from . import (
    BankAccount,
    BankConnector,
    SyncResult,
    Transaction,
    register_connector,
)

# Realistic Indian transaction templates
_TEMPLATES = [
    ("Swiggy Order", 349.0, "EXPENSE", "Food & Dining"),
    ("Zomato Payment", 425.0, "EXPENSE", "Food & Dining"),
    ("Amazon.in Purchase", 1299.0, "EXPENSE", "Shopping"),
    ("Flipkart Order", 899.0, "EXPENSE", "Shopping"),
    ("Jio Recharge", 299.0, "EXPENSE", "Utilities"),
    ("Airtel Broadband", 999.0, "EXPENSE", "Utilities"),
    ("Uber India", 187.0, "EXPENSE", "Transport"),
    ("Ola Ride", 215.0, "EXPENSE", "Transport"),
    ("Netflix Subscription", 649.0, "EXPENSE", "Entertainment"),
    ("Hotstar Premium", 299.0, "EXPENSE", "Entertainment"),
    ("BigBasket Groceries", 1875.0, "EXPENSE", "Groceries"),
    ("DMart Purchase", 2340.0, "EXPENSE", "Groceries"),
    ("NEFT-Salary Credit", 45000.0, "INCOME", None),
    ("UPI-Freelance Payment", 15000.0, "INCOME", None),
    ("IMPS-Rent Payment", 12000.0, "EXPENSE", "Housing"),
    ("PhonePe Transfer", 500.0, "EXPENSE", None),
    ("Google Pay UPI", 750.0, "EXPENSE", None),
    ("Electricity Bill BBPS", 1450.0, "EXPENSE", "Utilities"),
    ("LIC Premium", 3500.0, "EXPENSE", "Insurance"),
    ("SIP Mutual Fund", 5000.0, "EXPENSE", "Investment"),
]


@register_connector
class MockConnector(BankConnector):
    """Returns synthetic Indian bank data for testing."""

    @property
    def provider_name(self) -> str:
        return "mock"

    def create_consent(self, user_id: int, **kwargs: Any) -> dict:
        handle = f"mock-consent-{uuid.uuid4().hex[:12]}"
        return {
            "consent_handle": handle,
            "redirect_url": None,
            "status": "approved",
        }

    def check_consent_status(self, consent_handle: str, **kwargs: Any) -> str:
        return "approved"

    def fetch_accounts(self, consent_handle: str, **kwargs: Any) -> list[BankAccount]:
        return [
            BankAccount(
                account_id="mock-savings-001",
                label="HDFC Savings ****4321",
                type="savings",
                currency="INR",
            ),
            BankAccount(
                account_id="mock-current-002",
                label="ICICI Current ****8765",
                type="current",
                currency="INR",
            ),
        ]

    def fetch_transactions(
        self,
        consent_handle: str,
        account_id: str,
        from_date: date,
        to_date: date,
        **kwargs: Any,
    ) -> SyncResult:
        txns = _generate_transactions(from_date, to_date)
        cursor = to_date.isoformat()
        return SyncResult(
            transactions=txns,
            cursor=cursor,
            has_more=False,
        )

    def refresh_transactions(
        self,
        consent_handle: str,
        account_id: str,
        cursor: str | None,
        **kwargs: Any,
    ) -> SyncResult:
        if cursor:
            from_date = date.fromisoformat(cursor) + timedelta(days=1)
        else:
            from_date = date.today() - timedelta(days=30)
        to_date = date.today()

        if from_date > to_date:
            return SyncResult(transactions=[], cursor=cursor)

        txns = _generate_transactions(from_date, to_date)
        new_cursor = to_date.isoformat()
        return SyncResult(
            transactions=txns,
            cursor=new_cursor,
            has_more=False,
        )


def _generate_transactions(
    from_date: date,
    to_date: date,
) -> list[Transaction]:
    """Generate deterministic mock transactions for the date range."""
    txns: list[Transaction] = []
    day = from_date
    idx = 0
    while day <= to_date:
        count = (day.toordinal() % 3) + 1
        for _ in range(count):
            tmpl = _TEMPLATES[idx % len(_TEMPLATES)]
            desc, amount, etype, cat = tmpl
            jitter = ((idx * 7 + day.toordinal()) % 20) / 10.0
            txn_amount = round(amount * (0.9 + jitter * 0.1), 2)
            txns.append(
                Transaction(
                    txn_id=f"mock-{day.isoformat()}-{idx:04d}",
                    date=day.isoformat(),
                    amount=txn_amount,
                    description=f"{desc} - {day.strftime('%d %b')}",
                    currency="INR",
                    expense_type=etype,
                    category_hint=cat,
                )
            )
            idx += 1
        day += timedelta(days=1)
    return txns
