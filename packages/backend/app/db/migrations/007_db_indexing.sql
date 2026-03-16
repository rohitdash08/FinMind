-- Migration 007: Database indexing optimization for financial queries
-- Issue #128
-- Apply with: psql $DATABASE_URL -f migrations/007_db_indexing.sql
--
-- Analysis: most expensive query patterns in FinMind
--   1. GET /expenses?from=&to=&category_id=  → composite filter on user+date+category
--   2. GET /insights (monthly aggregates)     → group by user+month on expenses
--   3. GET /bills (active only, ordered)      → filter active, sort by due date
--   4. GET /reminders/run (pending dispatch)  → filter sent=false, send_at <= now
--   5. GET /categories (user lookup)          → filter by user_id
--   6. Recurring expense generation           → filter by user+active+cadence
--   7. Audit log queries                      → filter by user_id + action


-- ── expenses ────────────────────────────────────────────────────────────────

-- Basic user+date index — covers simple date-range queries that carry no
-- type or category filter (e.g. GET /expenses?from=&to=).
CREATE INDEX IF NOT EXISTS idx_expenses_user_spent_at
    ON expenses (user_id, spent_at DESC);

-- Category-filtered expense queries (GET /expenses?category_id=X)
CREATE INDEX IF NOT EXISTS idx_expenses_user_category
    ON expenses (user_id, category_id, spent_at DESC)
    WHERE category_id IS NOT NULL;

-- Income vs Expense type split (used by insights/dashboard)
CREATE INDEX IF NOT EXISTS idx_expenses_user_type_date
    ON expenses (user_id, expense_type, spent_at DESC);

-- Monthly aggregation (used by insights: GROUP BY year/month)
-- NOTE: DATE_TRUNC is a PostgreSQL-specific function.  This index will be
-- created successfully only on PostgreSQL and will fail on SQLite or MySQL.
-- On SQLite the test suite skips index-existence checks (see index_report.py).
CREATE INDEX IF NOT EXISTS idx_expenses_user_month
    ON expenses (user_id, DATE_TRUNC('month', spent_at));

-- Recurring source lookups (cascades, dedup checks)
CREATE INDEX IF NOT EXISTS idx_expenses_source_recurring
    ON expenses (source_recurring_id)
    WHERE source_recurring_id IS NOT NULL;

-- Amount range queries (future: analytics, budgeting)
CREATE INDEX IF NOT EXISTS idx_expenses_user_amount
    ON expenses (user_id, amount);


-- ── bills ────────────────────────────────────────────────────────────────────

-- Full (non-partial) user+due-date index — covers queries that do not
-- filter on active, e.g. admin views and historical reporting.
CREATE INDEX IF NOT EXISTS idx_bills_user_due
    ON bills (user_id, next_due_date);

-- Active bills only (most queries filter active=TRUE)
CREATE INDEX IF NOT EXISTS idx_bills_user_active_due
    ON bills (user_id, next_due_date)
    WHERE active = TRUE;

-- Autopay-enabled bills (background job filter)
CREATE INDEX IF NOT EXISTS idx_bills_autopay
    ON bills (user_id, next_due_date)
    WHERE autopay_enabled = TRUE AND active = TRUE;


-- ── reminders ────────────────────────────────────────────────────────────────

-- Full user+send_at index — supports per-user reminder listing and
-- queries that don't filter on sent status (e.g. history views).
CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders (user_id, send_at);

-- Pending reminders — the hot path for reminder dispatch job
-- Partial index: only unsent, non-permanently-failed rows
CREATE INDEX IF NOT EXISTS idx_reminders_pending_dispatch
    ON reminders (send_at, user_id)
    WHERE sent = FALSE;

-- Bill-reminder relationship lookups
CREATE INDEX IF NOT EXISTS idx_reminders_bill
    ON reminders (bill_id)
    WHERE bill_id IS NOT NULL;


-- ── recurring_expenses ────────────────────────────────────────────────────────

-- Full user+start_date index — supports historical queries and admin views
-- that list all recurring expenses regardless of active status.
CREATE INDEX IF NOT EXISTS idx_recurring_expenses_user_start
    ON recurring_expenses (user_id, start_date);

-- Active recurring expenses for generation jobs
CREATE INDEX IF NOT EXISTS idx_recurring_expenses_active
    ON recurring_expenses (user_id, cadence, start_date)
    WHERE active = TRUE;


-- ── categories ───────────────────────────────────────────────────────────────

-- User category listing (typically ordered by name)
CREATE INDEX IF NOT EXISTS idx_categories_user_name
    ON categories (user_id, name);


-- ── audit_logs ───────────────────────────────────────────────────────────────

-- User audit log queries (GDPR export, per-user audit)
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_created
    ON audit_logs (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- Action-based queries (monitoring, alerting)
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_created
    ON audit_logs (action, created_at DESC);


-- ── user_subscriptions ────────────────────────────────────────────────────────

-- Active subscription lookup (feature gating)
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_active
    ON user_subscriptions (user_id, active)
    WHERE active = TRUE;
