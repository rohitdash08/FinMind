-- Migration: Add accounts table and account_id to expenses
-- Issue: #132 - Multi-account financial overview dashboard

CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    account_type VARCHAR(20) NOT NULL DEFAULT 'CHECKING',
    balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    institution VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_accounts_user_active ON accounts(user_id, is_active);

-- Add account_id to expenses table (nullable for backward compatibility)
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id);
CREATE INDEX IF NOT EXISTS idx_expenses_account_id ON expenses(account_id);
