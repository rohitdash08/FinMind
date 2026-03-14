-- Migration: Add financial_accounts table for multi-account dashboard (#132)

DO $$ BEGIN
  CREATE TYPE account_type_enum AS ENUM ('BANK','CREDIT','CASH','INVESTMENT','WALLET','OTHER');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS financial_accounts (
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

CREATE INDEX IF NOT EXISTS idx_financial_accounts_user ON financial_accounts(user_id, active);

-- Add optional account_id FK to expenses for account-level filtering
ALTER TABLE expenses
  ADD COLUMN IF NOT EXISTS account_id INT REFERENCES financial_accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_expenses_account ON expenses(account_id);
