-- PostgreSQL schema for FinMind
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  preferred_currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  role VARCHAR(20) NOT NULL DEFAULT 'USER',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS preferred_currency VARCHAR(10) NOT NULL DEFAULT 'INR';

CREATE TABLE IF NOT EXISTS categories (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
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
CREATE INDEX IF NOT EXISTS idx_expenses_user_spent_at ON expenses(user_id, spent_at DESC);

ALTER TABLE expenses
  ADD COLUMN IF NOT EXISTS expense_type VARCHAR(20) NOT NULL DEFAULT 'EXPENSE';

DO $$ BEGIN
  CREATE TYPE recurring_cadence AS ENUM ('DAILY','WEEKLY','MONTHLY','YEARLY');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS recurring_expenses (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INT REFERENCES categories(id) ON DELETE SET NULL,
  amount NUMERIC(12,2) NOT NULL,
  currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  expense_type VARCHAR(20) NOT NULL DEFAULT 'EXPENSE',
  notes VARCHAR(500) NOT NULL,
  cadence recurring_cadence NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recurring_expenses_user_start ON recurring_expenses(user_id, start_date);

ALTER TABLE expenses
  ADD COLUMN IF NOT EXISTS source_recurring_id INT REFERENCES recurring_expenses(id) ON DELETE SET NULL;

DO $$ BEGIN
  CREATE TYPE bill_cadence AS ENUM ('MONTHLY','WEEKLY','YEARLY','ONCE');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS bills (
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
CREATE INDEX IF NOT EXISTS idx_bills_user_due ON bills(user_id, next_due_date);

ALTER TABLE bills
  ADD COLUMN IF NOT EXISTS autopay_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS reminders (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  bill_id INT REFERENCES bills(id) ON DELETE SET NULL,
  message VARCHAR(500) NOT NULL,
  send_at TIMESTAMP NOT NULL,
  sent BOOLEAN NOT NULL DEFAULT FALSE,
  channel VARCHAR(20) NOT NULL DEFAULT 'email'
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(user_id, sent, send_at);

CREATE TABLE IF NOT EXISTS ad_impressions (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE SET NULL,
  placement VARCHAR(100) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscription_plans (
  id SERIAL PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  price_cents INT NOT NULL,
  interval VARCHAR(20) NOT NULL DEFAULT 'monthly'
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id INT NOT NULL REFERENCES subscription_plans(id) ON DELETE RESTRICT,
  active BOOLEAN NOT NULL DEFAULT FALSE,
  started_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE SET NULL,
  action VARCHAR(100) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Bank Sync schema — append to packages/backend/app/db/schema.sql

CREATE TABLE IF NOT EXISTS bank_accounts (
    id                      VARCHAR(36)     PRIMARY KEY,
    user_id                 INTEGER         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider                VARCHAR(50)     NOT NULL,
    account_id              VARCHAR(255)    NOT NULL,
    masked_account_number   VARCHAR(50),
    bank_name               VARCHAR(100),
    ifsc                    VARCHAR(20),
    account_type            VARCHAR(30)     DEFAULT 'SAVINGS',
    currency                VARCHAR(10)     DEFAULT 'INR',
    holder_name             VARCHAR(100),
    consent_handle_id       VARCHAR(255),
    consent_artefact_id     VARCHAR(255),
    consent_status          VARCHAR(20)     DEFAULT 'PENDING',
    last_synced_at          DATE,
    created_at              TIMESTAMP       DEFAULT NOW(),
    updated_at              TIMESTAMP       DEFAULT NOW(),
    UNIQUE (user_id, provider, account_id)
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id                  VARCHAR(36)     PRIMARY KEY,
    bank_account_id     VARCHAR(36)     NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
    expense_id          INTEGER         REFERENCES expenses(id) ON DELETE SET NULL,
    transaction_id      VARCHAR(255)    NOT NULL,
    amount              NUMERIC(12, 2)  NOT NULL,
    currency            VARCHAR(10)     DEFAULT 'INR',
    transaction_type    VARCHAR(10)     NOT NULL CHECK (transaction_type IN ('DEBIT', 'CREDIT')),
    description         TEXT,
    date                DATE            NOT NULL,
    balance             NUMERIC(12, 2),
    category_hint       VARCHAR(100),
    raw                 JSONB,
    created_at          TIMESTAMP       DEFAULT NOW(),
    UNIQUE (bank_account_id, transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_bank_transactions_date         ON bank_transactions(date);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_account_date ON bank_transactions(bank_account_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_bank_accounts_user             ON bank_accounts(user_id);
