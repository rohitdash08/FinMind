# Collaborative Budgeting Feature

## Overview
The Collaborative Budgeting feature allows multiple users to contribute to a shared budget. Each user can add their contribution, and the system will track the total amount contributed, as well as the remaining budget. Once all users have contributed, the system calculates the balance for each user.

## Endpoints
- **POST /api/budget/contribution**: Allows a user to contribute to the budget.
- **GET /api/budget/remaining**: Returns the remaining budget after all contributions.
- **GET /api/budget/user_balance**: Retrieves the balance for a specific user.
- **POST /api/budget/settle**: Settles the budget by calculating the final balance for each user.

## Example Workflow
1. Create a collaborative budget.
2. Users add contributions.
3. View remaining budget.
4. Settle the budget to calculate user balances.

## Data Model
### CollaborativeBudget
- `budget_name`: The name of the collaborative budget (e.g., 'Vacation Fund').
- `users`: List of users contributing to the budget.
- `total_amount`: The total budget amount.
- `user_contributions`: A dictionary tracking individual user contributions.
