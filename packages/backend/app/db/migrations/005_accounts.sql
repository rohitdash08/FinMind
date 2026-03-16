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
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- Trigger to keep updated_at current on every row update
CREATE OR REPLACE FUNCTION _accounts_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS accounts_set_updated_at ON accounts;
CREATE TRIGGER accounts_set_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION _accounts_set_updated_at();

-- If the table already exists (re-run scenario), add the column idempotently.
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts (user_id, active);

-- Add account_id to expenses (nullable, backward-compatible)
ALTER TABLE expenses
    ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_expenses_account ON expenses (account_id)
    WHERE account_id IS NOT NULL;
