-- Migration: Database Indexing Optimization for Financial Queries
-- Issue #128: Improve performance of high-frequency queries
-- 
-- Analysis of query patterns in routes/expenses.py, routes/dashboard.py,
-- routes/bills.py, routes/reminders.py, routes/insights.py:
--
-- 1. Expenses: filtered by user_id + date range + category_id + notes ILIKE
-- 2. Dashboard: monthly aggregates by user_id + category_id + spent_at
-- 3. Bills: user_id + next_due_date + active
-- 4. Reminders: user_id + sent + send_at
-- 5. Insights: category-level spend aggregates by user

-- expenses: composite index for category filter queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_category_date
  ON expenses(user_id, category_id, spent_at DESC)
  WHERE category_id IS NOT NULL;

-- expenses: composite index for date range queries (most common pattern)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_date_type
  ON expenses(user_id, spent_at DESC, expense_type);

-- expenses: index on amount for aggregation queries (SUM, AVG per user)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_amount
  ON expenses(user_id, amount)
  INCLUDE (currency, spent_at);

-- expenses: partial index for notes search (only when notes is set)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_notes_trgm
  ON expenses USING gin(notes gin_trgm_ops)
  WHERE notes IS NOT NULL;

-- categories: index for user's category lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_categories_user_name
  ON categories(user_id, name);

-- recurring_expenses: index for active recurring items per user
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_recurring_expenses_user_active
  ON recurring_expenses(user_id, active, start_date)
  WHERE active = TRUE;

-- bills: composite index for upcoming bills query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bills_user_due_active
  ON bills(user_id, next_due_date, active)
  WHERE active = TRUE;

-- bills: index for autopay processing
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bills_autopay_due
  ON bills(next_due_date, autopay_enabled)
  WHERE active = TRUE AND autopay_enabled = TRUE;

-- reminders: composite index for pending reminders dispatch
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminders_pending_dispatch
  ON reminders(send_at, sent, channel)
  WHERE sent = FALSE;

-- reminders: composite for user's pending reminders
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminders_user_pending
  ON reminders(user_id, sent, send_at)
  WHERE sent = FALSE;

-- audit_logs: index for user audit history lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_user_created
  ON audit_logs(user_id, created_at DESC)
  WHERE user_id IS NOT NULL;

-- ad_impressions: index for user impression count queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ad_impressions_user_created
  ON ad_impressions(user_id, created_at DESC)
  WHERE user_id IS NOT NULL;

-- Enable pg_trgm extension for fuzzy text search on notes
-- (needed for the gin_trgm_ops index above)
CREATE EXTENSION IF NOT EXISTS pg_trgm;