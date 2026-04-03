-- Migration: Multi-Account Financial Overview
-- Issue #132: Allow users to track multiple financial accounts

CREATE TABLE IF NOT EXISTS financial_accounts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    account_type VARCHAR(30) NOT NULL DEFAULT 'checking',
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    opening_balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    color VARCHAR(20),
    icon VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_financial_accounts_user
    ON financial_accounts(user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_financial_accounts_type
    ON financial_accounts(user_id, account_type)
    WHERE is_active = TRUE;

-- Account type constraint
ALTER TABLE financial_accounts
    DROP CONSTRAINT IF EXISTS chk_account_type;
ALTER TABLE financial_accounts
    ADD CONSTRAINT chk_account_type
    CHECK (account_type IN ('checking', 'savings', 'credit_card', 'investment', 'cash', 'other'));