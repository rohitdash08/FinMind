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

CREATE TABLE IF NOT EXISTS devices (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  fingerprint VARCHAR(255) NOT NULL,
  user_agent VARCHAR(500),
  ip_address VARCHAR(45),
  accept_language VARCHAR(100),
  trust_score INT NOT NULL DEFAULT 0,
  last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_devices_user_fingerprint ON devices(user_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_devices_user_ip ON devices(user_id, ip_address);

DO $$ BEGIN
  CREATE TYPE login_attempt_level AS ENUM ('INFO','SUSPICIOUS','BLOCKED');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS login_attempts (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE SET NULL,
  email VARCHAR(255) NOT NULL,
  ip_address VARCHAR(45),
  user_agent VARCHAR(500),
  location VARCHAR(255),
  success BOOLEAN NOT NULL DEFAULT FALSE,
  level login_attempt_level NOT NULL DEFAULT 'INFO',
  reason VARCHAR(500),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_user ON login_attempts(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, created_at DESC);

CREATE TABLE IF NOT EXISTS suspicious_activities (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  activity_type VARCHAR(100) NOT NULL,
  description VARCHAR(500) NOT NULL,
  severity VARCHAR(20) NOT NULL DEFAULT 'medium',
  acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  metadata_json TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_suspicious_activities_user ON suspicious_activities(user_id, created_at DESC);

DO $$ BEGIN
  CREATE TYPE reminder_delivery_status AS ENUM ('PENDING','SENT','DELIVERED','CLICKED','FAILED');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS reminder_deliveries (
  id SERIAL PRIMARY KEY,
  reminder_id INT NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel VARCHAR(20) NOT NULL,
  status reminder_delivery_status NOT NULL DEFAULT 'PENDING',
  attempt_count INT NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMP,
  delivered_at TIMESTAMP,
  clicked_at TIMESTAMP,
  error_message VARCHAR(500),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reminder_deliveries_user ON reminder_deliveries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reminder_deliveries_status ON reminder_deliveries(user_id, status);

DO $$ BEGIN
  CREATE TYPE notification_priority AS ENUM ('URGENT','HIGH','NORMAL','LOW');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS notifications (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR(200) NOT NULL,
  body VARCHAR(1000) NOT NULL,
  notification_type VARCHAR(50) NOT NULL DEFAULT 'general',
  priority notification_priority NOT NULL DEFAULT 'NORMAL',
  group_key VARCHAR(100),
  read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, read, priority);

CREATE TABLE IF NOT EXISTS spending_categories (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  is_essential BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, category_id)
);

CREATE TABLE IF NOT EXISTS savings_suggestions (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  suggestion_type VARCHAR(50) NOT NULL,
  title VARCHAR(200) NOT NULL,
  description VARCHAR(1000) NOT NULL,
  estimated_savings NUMERIC(12,2),
  dismissed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_savings_suggestions_user ON savings_suggestions(user_id, created_at DESC);
