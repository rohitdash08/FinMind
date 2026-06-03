"""
Multi-account financial overview dashboard
"""
from datetime import datetime, timezone
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class Account:
    id: str
    name: str
    type: str  # checking, savings, investment, credit
    balance: float
    currency: str
    last_updated: datetime


@dataclass
class DashboardSummary:
    total_balance: float
    accounts: List[Account]
    by_type: Dict[str, float]
    currency: str
    last_updated: datetime


def get_user_accounts(user_id: str) -> List[Account]:
    """Get all accounts for a user"""
    return [
        Account(
            id="acc_1",
            name="Main Checking",
            type="checking",
            balance=5000.00,
            currency="USD",
            last_updated=datetime.now(timezone.utc)
        ),
        Account(
            id="acc_2",
            name="Savings",
            type="savings",
            balance=15000.00,
            currency="USD",
            last_updated=datetime.now(timezone.utc)
        ),
        Account(
            id="acc_3",
            name="Investment Portfolio",
            type="investment",
            balance=50000.00,
            currency="USD",
            last_updated=datetime.now(timezone.utc)
        )
    ]


def get_dashboard_summary(user_id: str) -> DashboardSummary:
    """Get financial overview for all accounts"""
    accounts = get_user_accounts(user_id)
    total_balance = sum(acc.balance for acc in accounts)
    by_type = {}
    for acc in accounts:
        by_type[acc.type] = by_type.get(acc.type, 0) + acc.balance
    
    return DashboardSummary(
        total_balance=total_balance,
        accounts=accounts,
        by_type=by_type,
        currency="USD",
        last_updated=datetime.now(timezone.utc)
    )


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format currency for display"""
    if currency == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.2f} {currency}"
