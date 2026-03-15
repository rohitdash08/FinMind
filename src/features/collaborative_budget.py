from typing import List, Dict

class CollaborativeBudget:
    def __init__(self, budget_name: str, users: List[str], total_amount: float) -> None:
        self.budget_name = budget_name
        self.users = users
        self.total_amount = total_amount
        self.user_contributions = {user: 0.0 for user in users}

    def add_contribution(self, user: str, amount: float) -> None:
        if user not in self.users:
            raise ValueError(f'User {user} is not part of the collaborative budget.')
        if amount < 0:
            raise ValueError('Contribution amount must be positive.')
        self.user_contributions[user] += amount

    def get_remaining_budget(self) -> float:
        total_contributed = sum(self.user_contributions.values())
        return self.total_amount - total_contributed

    def get_user_balance(self, user: str) -> float:
        if user not in self.users:
            raise ValueError(f'User {user} is not part of the collaborative budget.')
        return self.user_contributions[user]

    def settle_budget(self) -> Dict[str, float]:
        total_contributed = sum(self.user_contributions.values())
        if total_contributed < self.total_amount:
            raise ValueError('Total contributions do not match the total budget amount.')
        equal_share = self.total_amount / len(self.users)
        balance = {user: self.user_contributions[user] - equal_share for user in self.users}
        return balance

    def __str__(self) -> str:
        return f'Collaborative Budget: {self.budget_name} | Total: {self.total_amount} | Users: {self.users}'