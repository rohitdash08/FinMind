

# FinMind Database Schema Reference

This document provides a high-level overview of the database schema for FinMind, focusing on the core tables: Users, Expenses, Bills, and Budgets.

## Users Table

The `users` table stores user account information:

```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  preferred_currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  role VARCHAR(20) NOT NULL DEFAULT 'USER',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Key Fields:**
- `id`: Unique identifier for the user
- `email`: User's email address (unique)
- `password_hash`: Securely hashed password
- `preferred_currency`: Default currency for financial transactions (default: INR)
- `role`: User role (USER or ADMIN)
- `created_at`: Timestamp when the user account was created

## Expenses Table

The `expenses` table tracks individual financial transactions:

```sql
CREATE TABLE expenses (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INT REFERENCES categories(id) ON DELETE SET NULL,
  amount NUMERIC(12,2) NOT NULL,
  currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  expense_type VARCHAR(20) NOT NULL DEFAULT 'EXPENSE',
  notes VARCHAR(500),
  spent_at DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Key Fields:**
- `id`: Unique identifier for the expense
- `user_id`: Foreign key to the user who recorded the expense
- `category_id`: Foreign key to expense category (optional)
- `amount`: Monetary amount of the expense
- `currency`: Currency type (default: INR)
- `expense_type`: Type of transaction (default: EXPENSE)
- `notes`: Optional description of the expense
- `spent_at`: Date when the expense was incurred
- `created_at`: Timestamp when the expense was recorded

## Bills Table

The `bills` table manages recurring payments and financial obligations:

```sql
CREATE TABLE bills (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(200) NOT NULL,
  amount NUMERIC(12,2) NOT NULL,
  currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  next_due_date DATE NOT NULL,
  cadence bill_cadence NOT NULL,
  autopay_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  channel_whatsapp BOOLEAN NOT NULL DEFAULT FALSE,
  channel_email BOOLEAN NOT NULL DEFAULT TRUE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Key Fields:**
- `id`: Unique identifier for the bill
- `user_id`: Foreign key to the user who owns the bill
- `name`: Description of the bill (e.g., "Electricity Bill")
- `amount`: Amount due for the bill
- `currency`: Currency type (default: INR)
- `next_due_date`: When the bill is due
- `cadence`: How often the bill recurs (MONTHLY, WEEKLY, YEARLY, ONCE)
- `autopay_enabled`: Whether autopay is enabled
- `channel_whatsapp`: Whether WhatsApp notifications are enabled
- `channel_email`: Whether email notifications are enabled
- `active`: Whether the bill is currently active
- `created_at`: Timestamp when the bill was created

## Budgets Table

*Note: While the current implementation doesn't have a dedicated budgets table, budgeting functionality is implemented through:*

1. **Categories** table (for expense categorization)
2. **Recurring Expenses** table (for planned expenses)
3. **Bills** table (for planned payments)

The budgeting system works by:
- Tracking expenses by category
- Comparing actual spending against planned recurring expenses
- Providing insights based on spending patterns

### Budgeting Implementation Details

1. **Categories** table allows users to define spending categories
2. **Recurring Expenses** table enables users to set up regular expenses
3. **Bills** table manages recurring payments with notification options

The application provides budgeting insights through:
- Monthly spend analysis
- Category breakdowns
- AI-powered budget suggestions

## Relationships

The database schema includes several important relationships:
- Users can have multiple expenses, bills, and categories
- Expenses can be associated with categories
- Bills can have reminders
- Users can have multiple subscriptions

## Indexes

The schema includes indexes for performance optimization:
- `idx_expenses_user_spent_at`: For efficient expense queries by user and date
- `idx_bills_user_due`: For efficient bill queries by user and due date
- `idx_reminders_due`: For efficient reminder queries

## Summary

This database schema provides a comprehensive foundation for FinMind's financial tracking and budgeting features, supporting:
- User authentication and profile management
- Expense tracking with categorization
- Bill management with recurring payment support
- Reminder notifications
- Budgeting insights and financial analysis

Completed DB schema reference for [rohitdash08/FinMind]

