# Multi-Account Financial Overview Dashboard

## Overview

This feature adds multi-account financial tracking to FinMind, allowing users to manage multiple financial accounts (bank, credit card, cash, investment, wallet) in a single unified dashboard view.

## Features

- **Account Management**: Full CRUD operations for financial accounts
- **Account Types**: Bank, Credit Card, Cash, Investment, Wallet, Other
- **Net Worth Tracking**: Automatic calculation of assets minus liabilities
- **Aggregated Overview**: Total balance breakdown by account type and currency
- **Recent Transactions**: Last 10 expenses across all accounts
- **Color-Coded Accounts**: Each account has a customizable color for visual distinction
- **Soft Delete**: Accounts are deactivated rather than permanently deleted to preserve history

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/accounts` | List all active accounts |
| `POST` | `/accounts` | Create a new account |
| `GET` | `/accounts/:id` | Get account details |
| `PATCH` | `/accounts/:id` | Update account |
| `DELETE` | `/accounts/:id` | Soft-delete (deactivate) |
| `GET` | `/accounts/overview` | Aggregated multi-account view |

### POST /accounts — Request Body

```json
{
  "name": "Main Checking",
  "account_type": "BANK",
  "currency": "USD",
  "balance": 5000.00,
  "institution": "Chase",
  "last_four": "4321",
  "color": "#10B981"
}
```

### GET /accounts/overview — Response

```json
{
  "total_accounts": 3,
  "total_assets": 15000.00,
  "total_liabilities": 2000.00,
  "net_worth": 13000.00,
  "by_type": {
    "BANK": { "count": 2, "total_balance": 15000.0 },
    "CREDIT": { "count": 1, "total_balance": 2000.0 }
  },
  "by_currency": { "USD": 13000.0 },
  "accounts": [...],
  "recent_transactions": [...]
}
```

## Database Schema

```sql
CREATE TABLE financial_accounts (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(200) NOT NULL,
  account_type VARCHAR(20) NOT NULL DEFAULT 'BANK',
  currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  balance NUMERIC(14,2) NOT NULL DEFAULT 0,
  institution VARCHAR(200),
  last_four VARCHAR(4),
  color VARCHAR(7) NOT NULL DEFAULT '#3B82F6',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

## Net Worth Calculation

- **Assets** = Sum of balances for BANK, CASH, INVESTMENT, WALLET, OTHER accounts
- **Liabilities** = Sum of absolute balances for CREDIT accounts
- **Net Worth** = Assets − Liabilities

## Testing

### Backend (25 tests)
```bash
sh ./scripts/test-backend.sh tests/test_accounts.py
```

Tests cover:
- Create: minimal, all fields, initial balance, validation errors, auth required
- List: empty, own accounts, user isolation, auth required
- Get: own, 404 for other user, 404 for nonexistent
- Update: name, type+currency, empty name rejected, 404 for other user
- Delete: soft delete, 404 for other user
- Overview: empty state, balance aggregation, by_type grouping, auth required, user isolation

### Frontend (6 tests)
```bash
cd app && npx vitest run src/__tests__/accounts.test.ts
```

## Migration

Apply migration to existing PostgreSQL databases:
```bash
psql $DATABASE_URL < packages/backend/app/db/002_financial_accounts.sql
```

## Files Changed

### Backend
- `packages/backend/app/models.py` — Added `AccountType` enum and `FinancialAccount` model
- `packages/backend/app/routes/accounts.py` — New blueprint with CRUD + overview
- `packages/backend/app/routes/__init__.py` — Registered accounts blueprint
- `packages/backend/app/db/002_financial_accounts.sql` — SQL migration
- `packages/backend/tests/test_accounts.py` — 25 test cases

### Frontend
- `app/src/api/accounts.ts` — Typed API client module
- `app/src/pages/AccountsOverview.tsx` — Full dashboard page with create dialog
- `app/src/App.tsx` — Added `/accounts` route
- `app/src/components/layout/Navbar.tsx` — Added Accounts nav link
- `app/src/__tests__/accounts.test.ts` — 6 API tests

### Documentation
- `docs/multi-account-dashboard.md` — This file
