"""Expense Sharing & Split Service.

Split expenses between friends/groups:
- Equal, percentage, and custom splits
- Group management (create, join, leave)
- Debt simplification (minimize transactions)
- Settlement tracking
- Balance calculation
- Payment reminders
"""

import logging
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.sharing")


class SplitType(str, Enum):
    EQUAL = "equal"
    PERCENTAGE = "percentage"
    CUSTOM = "custom"
    SHARES = "shares"


class ExpenseStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    SETTLED = "settled"


class Group:
    def __init__(self, group_id: str, name: str, creator_id: str):
        self.group_id = group_id
        self.name = name
        self.creator_id = creator_id
        self.members = [creator_id]
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "group_id": self.group_id,
            "name": self.name,
            "creator_id": self.creator_id,
            "members": self.members,
            "created_at": self.created_at,
        }


class SharedExpense:
    def __init__(self, expense_id: str, group_id: str, payer_id: str,
                 total_amount: float, description: str, split_type: str,
                 splits: dict, category: str = ""):
        self.expense_id = expense_id
        self.group_id = group_id
        self.payer_id = payer_id
        self.total_amount = total_amount
        self.description = description
        self.split_type = split_type
        self.splits = splits  # {user_id: amount}
        self.category = category
        self.created_at = datetime.utcnow().isoformat()
        self.settlements = {}  # {user_id: amount_paid_back}

    @property
    def status(self):
        total_owed = sum(self.splits.values()) - self.splits.get(self.payer_id, 0)
        total_settled = sum(self.settlements.values())
        if total_settled >= total_owed - 0.01:
            return ExpenseStatus.SETTLED.value
        elif total_settled > 0:
            return ExpenseStatus.PARTIAL.value
        return ExpenseStatus.PENDING.value

    def to_dict(self):
        return {
            "expense_id": self.expense_id,
            "group_id": self.group_id,
            "payer_id": self.payer_id,
            "total_amount": round(self.total_amount, 2),
            "description": self.description,
            "split_type": self.split_type,
            "splits": {k: round(v, 2) for k, v in self.splits.items()},
            "category": self.category,
            "created_at": self.created_at,
            "status": self.status,
            "settlements": {k: round(v, 2) for k, v in self.settlements.items()},
            "remaining": round(sum(self.splits.values()) - self.splits.get(self.payer_id, 0)
                              - sum(self.settlements.values()), 2),
        }


class ExpenseSharingService:
    """Manage expense sharing and splitting."""

    def __init__(self):
        self.groups = {}
        self.expenses = {}

    def create_group(self, name: str, creator_id: str) -> dict:
        """Create a new expense group."""
        group_id = str(uuid4())[:8]
        group = Group(group_id, name, creator_id)
        self.groups[group_id] = group
        return group.to_dict()

    def join_group(self, group_id: str, user_id: str) -> dict:
        """Join an existing group."""
        if group_id not in self.groups:
            return {"error": "Group not found"}

        group = self.groups[group_id]
        if user_id not in group.members:
            group.members.append(user_id)
        return {"status": "joined", "group": group.to_dict()}

    def leave_group(self, group_id: str, user_id: str) -> dict:
        """Leave a group."""
        if group_id not in self.groups:
            return {"error": "Group not found"}

        group = self.groups[group_id]
        if user_id in group.members and user_id != group.creator_id:
            group.members.remove(user_id)
        return {"status": "left"}

    def split_expense(self, payer_id: str, total_amount: float,
                       description: str, split_type: str,
                       participants: list[str],
                       custom_splits: dict = None,
                       group_id: str = None,
                       category: str = "") -> dict:
        """Split an expense among participants."""
        expense_id = str(uuid4())[:8]

        if split_type == SplitType.EQUAL.value:
            per_person = total_amount / max(len(participants), 1)
            splits = {uid: per_person for uid in participants}

        elif split_type == SplitType.PERCENTAGE.value:
            splits = {}
            if custom_splits:
                for uid, pct in custom_splits.items():
                    if uid in participants:
                        splits[uid] = total_amount * float(pct) / 100
            # Distribute remainder
            allocated = sum(splits.values())
            if abs(allocated - total_amount) > 0.01 and participants:
                remaining = total_amount - allocated
                unsplit = [p for p in participants if p not in splits]
                if unsplit:
                    per_unsplit = remaining / len(unsplit)
                    for uid in unsplit:
                        splits[uid] = per_unsplit

        elif split_type == SplitType.CUSTOM.value or split_type == SplitType.SHARES.value:
            splits = custom_splits or {uid: 0 for uid in participants}

        else:
            per_person = total_amount / max(len(participants), 1)
            splits = {uid: per_person for uid in participants}

        expense = SharedExpense(
            expense_id=expense_id,
            group_id=group_id or "",
            payer_id=payer_id,
            total_amount=total_amount,
            description=description,
            split_type=split_type,
            splits=splits,
            category=category,
        )

        self.expenses[expense_id] = expense
        return expense.to_dict()

    def settle(self, expense_id: str, user_id: str, amount: float) -> dict:
        """Record a settlement payment."""
        if expense_id not in self.expenses:
            return {"error": "Expense not found"}

        expense = self.expenses[expense_id]
        expense.settlements[user_id] = expense.settlements.get(user_id, 0) + amount
        return {"status": "recorded", "expense": expense.to_dict()}

    def get_balance(self, group_id: str = None) -> dict:
        """Calculate balances (who owes whom)."""
        balances = defaultdict(float)

        for expense in self.expenses.values():
            if group_id and expense.group_id != group_id:
                continue

            payer = expense.payer_id
            for uid, amount in expense.splits.items():
                settled = expense.settlements.get(uid, 0)
                remaining = amount - settled

                if uid == payer:
                    continue  # Payer doesn't owe themselves

                if remaining > 0.01:
                    balances[uid] -= remaining  # owes
                    balances[payer] += remaining  # is owed

        # Simplify debts
        simplified = self._simplify_debts(balances)

        return {
            "balances": {k: round(v, 2) for k, v in balances.items()},
            "simplified_debts": simplified,
            "total_owed": round(sum(v for v in balances.values() if v < 0) * -1, 2),
        }

    def _simplify_debts(self, balances: dict) -> list[dict]:
        """Simplify debts to minimize number of transactions."""
        debtors = [(uid, -amt) for uid, amt in balances.items() if amt < -0.01]
        creditors = [(uid, amt) for uid, amt in balances.items() if amt > 0.01]

        debtors.sort(key=lambda x: x[1], reverse=True)
        creditors.sort(key=lambda x: x[1], reverse=True)

        transactions = []
        i = j = 0

        while i < len(debtors) and j < len(creditors):
            debtor_id, debt = debtors[i]
            creditor_id, credit = creditors[j]
            amount = min(debt, credit)

            transactions.append({
                "from": debtor_id,
                "to": creditor_id,
                "amount": round(amount, 2),
            })

            debtors[i] = (debtor_id, debt - amount)
            creditors[j] = (creditor_id, credit - amount)

            if debtors[i][1] < 0.01:
                i += 1
            if creditors[j][1] < 0.01:
                j += 1

        return transactions

    def get_user_expenses(self, user_id: str) -> list[dict]:
        """Get all expenses involving a user."""
        result = []
        for expense in self.expenses.values():
            if user_id in expense.splits or user_id == expense.payer_id:
                result.append(expense.to_dict())
        return result

    def get_group_summary(self, group_id: str) -> dict:
        """Get summary for a group."""
        if group_id not in self.groups:
            return {"error": "Group not found"}

        group = self.groups[group_id]
        group_expenses = [e for e in self.expenses.values() if e.group_id == group_id]
        balance = self.get_balance(group_id)

        return {
            "group": group.to_dict(),
            "expense_count": len(group_expenses),
            "total_spent": round(sum(e.total_amount for e in group_expenses), 2),
            "balance": balance,
        }
