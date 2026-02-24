-- Migration 001: Database indexing optimization for financial queries
-- Issue #128
--
-- Adds composite indexes to accelerate the most common query patterns
-- identified across dashboard, expenses, bills, reminders, and budgets routes.

-- ==========================================================================
-- expenses table
-- ==========================================================================

-- Dashboard: monthly income/expense aggregation filtered by user + year/month + type
-- Also speeds up category breakdown queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_type_spent
    ON expenses (user_id, expense_type, spent_at);

-- Expenses list: filter by user + category + date range
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_category_spent
    ON expenses (user_id, category_id, spent_at DESC);

-- Recurring expense generation: duplicate check by user + source + date
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_recurring_spent
    ON expenses (user_id, source_recurring_id, spent_at)
    WHERE source_recurring_id IS NOT NULL;

-- Import duplicate detection: user + date + amount + notes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_expenses_user_date_amount
    ON expenses (user_id, spent_at, amount);

-- ==========================================================================
-- bills table
-- ==========================================================================

-- Dashboard & list: active bills for a user ordered by due date
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bills_user_active_due
    ON bills (user_id, next_due_date)
    WHERE active = TRUE;

-- ==========================================================================
-- recurring_expenses table
-- ==========================================================================

-- List active recurring expenses for a user
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_recurring_user_active
    ON recurring_expenses (user_id, created_at DESC)
    WHERE active = TRUE;

-- ==========================================================================
-- categories table
-- ==========================================================================

-- Unique-per-user name lookups and alphabetical listing
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_categories_user_name
    ON categories (user_id, name);

-- ==========================================================================
-- reminders table
-- ==========================================================================

-- Pending reminders lookup (scheduler)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminders_pending
    ON reminders (send_at)
    WHERE sent = FALSE;

-- ==========================================================================
-- budgets table (if exists)
-- ==========================================================================

-- Budget lookup by user + category (already has unique constraint, but add
-- a covering index for period lookups)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_budgets_user_category
    ON budgets (user_id, category_id, period);

-- ==========================================================================
-- audit_logs table
-- ==========================================================================

-- Filter audit logs by user and time
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_user_created
    ON audit_logs (user_id, created_at DESC);
