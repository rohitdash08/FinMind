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

DO $$ BEGIN
  CREATE TYPE bank_conn_status AS ENUM ('active', 'error', 'disconnected');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS bank_connections (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  connector_name VARCHAR(50) NOT NULL,
  display_name VARCHAR(200) NOT NULL,
  status bank_conn_status NOT NULL DEFAULT 'active',
  config_encrypted TEXT,
  last_refresh_at TIMESTAMP,
  last_error TEXT,
  institution_name VARCHAR(200),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bank_connections_user ON bank_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_bank_connections_connector ON bank_connections(connector_name);

CREATE TABLE IF NOT EXISTS bank_connection_accounts (
  id SERIAL PRIMARY KEY,
  bank_connection_id INT NOT NULL REFERENCES bank_connections(id) ON DELETE CASCADE,
  external_account_id VARCHAR(100) NOT NULL,
  account_name VARCHAR(200) NOT NULL,
  account_type VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
  currency VARCHAR(10) NOT NULL DEFAULT 'USD',
  current_balance NUMERIC(12,2),
  mask VARCHAR(10),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bca_connection ON bank_connection_accounts(bank_connection_id);

CREATE TABLE IF NOT EXISTS bank_import_runs (
  id SERIAL PRIMARY KEY,
  bank_connection_id INT NOT NULL REFERENCES bank_connections(id) ON DELETE CASCADE,
  account_id INT NOT NULL REFERENCES bank_connection_accounts(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  imported_count INT NOT NULL DEFAULT 0,
  duplicate_count INT NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'started',
  error_message TEXT,
  started_at TIMESTAMP NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bank_import_runs_connection ON bank_import_runs(bank_connection_id);
CREATE INDEX IF NOT EXISTS idx_bank_import_runs_user ON bank_import_runs(user_id);

-- Webhook subscriptions
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  url VARCHAR(2048) NOT NULL,
  secret VARCHAR(255) NOT NULL,
  events TEXT NOT NULL,  -- JSON array of event types
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_user ON webhook_subscriptions(user_id);

-- Webhook deliveries (for retry tracking)
CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id SERIAL PRIMARY KEY,
  subscription_id INT NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
  event_type VARCHAR(100) NOT NULL,
  payload TEXT NOT NULL,  -- JSON payload
  status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, success, failed
  attempts INT NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMP,
  response_status INT,
  response_body TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_subscription ON webhook_deliveries(subscription_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status);
