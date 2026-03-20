-- Migration: 002_add_indexes
-- Description: Add database indexes for financial query optimization (issue #128)
--
-- This migration adds single-column and composite indexes to speed up the most
-- common query patterns identified in the application routes:
--
--   1. Expense listing: filter by user_id, date range, category; sort by spent_at
--   2. Dashboard aggregations: SUM grouped by user_id + expense_type + month
--   3. Recurring expense generation: dedup on user_id + source_recurring_id + spent_at
--   4. Bill listing: filter by user_id + active, sort by next_due_date
--   5. Reminder processing: filter by user_id + sent + send_at
--   6. Reminder dedup: user_id + bill_id + channel + send_at
--
-- All statements are idempotent (IF NOT EXISTS).

BEGIN;

-- ============================================================
-- users
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_users_created_at ON users(created_at);

-- ============================================================
-- categories
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_categories_user_id ON categories(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_categories_user_id_name ON categories(user_id, name);

-- ============================================================
-- expenses  (heaviest table)
-- ============================================================
-- Single-column indexes for foreign keys and date filtering
CREATE INDEX IF NOT EXISTS ix_expenses_user_id ON expenses(user_id);
CREATE INDEX IF NOT EXISTS ix_expenses_category_id ON expenses(category_id);
CREATE INDEX IF NOT EXISTS ix_expenses_spent_at ON expenses(spent_at);

-- Composite: list expenses by user + date range  (covers ORDER BY spent_at DESC)
CREATE INDEX IF NOT EXISTS ix_expenses_user_id_spent_at ON expenses(user_id, spent_at);

-- Composite: filter by user + category
CREATE INDEX IF NOT EXISTS ix_expenses_user_id_category_id ON expenses(user_id, category_id);

-- Composite: dashboard SUM aggregations  (user + expense_type + month extraction)
CREATE INDEX IF NOT EXISTS ix_expenses_user_id_type_spent_at ON expenses(user_id, expense_type, spent_at);

-- Composite: duplicate detection during recurring expense generation
CREATE INDEX IF NOT EXISTS ix_expenses_user_id_recurring_spent_at ON expenses(user_id, source_recurring_id, spent_at);

-- ============================================================
-- recurring_expenses
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_recurring_expenses_user_id ON recurring_expenses(user_id);
CREATE INDEX IF NOT EXISTS ix_recurring_expenses_user_id_active ON recurring_expenses(user_id, active);

-- ============================================================
-- bills
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_bills_user_id ON bills(user_id);
CREATE INDEX IF NOT EXISTS ix_bills_user_id_active_due ON bills(user_id, active, next_due_date);

-- ============================================================
-- reminders
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_reminders_user_id ON reminders(user_id);
CREATE INDEX IF NOT EXISTS ix_reminders_user_id_sent_send_at ON reminders(user_id, sent, send_at);
CREATE INDEX IF NOT EXISTS ix_reminders_user_id_bill_id_channel_send_at ON reminders(user_id, bill_id, channel, send_at);

-- ============================================================
-- ad_impressions
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_ad_impressions_user_id ON ad_impressions(user_id);
CREATE INDEX IF NOT EXISTS ix_ad_impressions_created_at ON ad_impressions(created_at);

-- ============================================================
-- user_subscriptions
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_user_subscriptions_user_id ON user_subscriptions(user_id);

-- ============================================================
-- audit_logs
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id_created_at ON audit_logs(user_id, created_at);

COMMIT;
