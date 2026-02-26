-- Migration: Add financial_accounts table for multi-account support

CREATE TABLE IF NOT EXISTS financial_accounts (
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

CREATE INDEX IF NOT EXISTS idx_financial_accounts_user_id ON financial_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_financial_accounts_user_active ON financial_accounts(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_financial_accounts_type ON financial_accounts(account_type);
