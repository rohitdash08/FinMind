-- Migration 005: Multi-account financial overview
-- Issue #132
-- Apply with: psql $DATABASE_URL -f migrations/005_accounts.sql

CREATE TABLE IF NOT EXISTS accounts (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(200)  NOT NULL,
    account_type    VARCHAR(20)   NOT NULL DEFAULT 'BANK',
    currency        VARCHAR(10)   NOT NULL DEFAULT 'INR',
    initial_balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    color           VARCHAR(20)   NULL,
    active          BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts (user_id, active);

-- Add account_id to expenses (nullable, backward-compatible)
ALTER TABLE expenses
    ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_expenses_account ON expenses (account_id)
    WHERE account_id IS NOT NULL;
