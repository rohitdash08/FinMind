# Multi-Account Financial Overview Dashboard

## Overview

This feature adds support for managing multiple financial accounts (checking, savings, credit cards, etc.) and viewing them in a unified dashboard.

## Features

- **Account Management**: Create, read, update, and delete financial accounts
- **Multiple Account Types**: Support for checking, savings, credit card, cash, investment, loan, and other account types
- **Multi-Currency Support**: Track accounts in different currencies
- **Aggregated Overview**: View total balances by currency and account type
- **Recent Activity**: See recent expenses and upcoming bills across all accounts

## API Endpoints

### Create Account
```http
POST /accounts
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Main Checking",
  "account_type": "CHECKING",
  "balance": 5000,
  "currency": "USD",
  "institution": "Chase Bank",
  "account_number_last4": "1234",
  "color": "#4CAF50",
  "icon": "bank"
}
```

### List Accounts
```http
GET /accounts
Authorization: Bearer <token>
```

### Get Single Account
```http
GET /accounts/{account_id}
Authorization: Bearer <token>
```

### Update Account
```http
PUT /accounts/{account_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Updated Name",
  "balance": 6000
}
```

### Delete Account (Soft Delete)
```http
DELETE /accounts/{account_id}
Authorization: Bearer <token>
```

### Get Multi-Account Overview
```http
GET /accounts/overview
Authorization: Bearer <token>
```

Response:
```json
{
  "accounts": [...],
  "summary": {
    "total_accounts": 3,
    "totals_by_currency": {
      "USD": 15000,
      "EUR": 3000
    },
    "totals_by_type": {
      "CHECKING": 8000,
      "SAVINGS": 10000
    }
  },
  "recent_expenses": [...],
  "upcoming_bills": [...]
}
```

## Account Types

- `CHECKING`: Checking account
- `SAVINGS`: Savings account
- `CREDIT_CARD`: Credit card
- `CASH`: Cash
- `INVESTMENT`: Investment account
- `LOAN`: Loan account
- `OTHER`: Other account types

## Database Schema

```sql
CREATE TABLE financial_accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    account_type VARCHAR(20) NOT NULL DEFAULT 'CHECKING',
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    institution VARCHAR(200),
    account_number_last4 VARCHAR(4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    color VARCHAR(7),
    icon VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

## Testing

Run tests:
```bash
cd packages/backend
pytest tests/test_accounts.py -v
```

## Implementation Details

### Backend
- **Models**: `FinancialAccount` model in `app/models_accounts.py`
- **Routes**: Account management endpoints in `app/routes/accounts.py`
- **Tests**: Comprehensive test coverage in `tests/test_accounts.py`

### Security
- All endpoints require JWT authentication
- Users can only access their own accounts
- Soft delete (deactivation) instead of hard delete for data integrity

## Future Enhancements

- Account linking with expenses and bills
- Transaction history per account
- Account balance tracking over time
- Budget allocation per account
- Account sharing for household management
- Bank integration via Plaid/Yodlee
