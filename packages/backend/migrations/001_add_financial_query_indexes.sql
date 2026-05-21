-- Migration: Add database indexes for high-frequency financial queries
-- Issue: #128 - Database indexing optimization for financial queries
-- Description: Adds composite indexes to support the most common query patterns
--              in the FinMind application, improving dashboard, expense listing,
--              recurring expense generation, and duplicate detection performance.

-- Expense table: primary workhorse - most queries start with user_id
-- Covers: list_expenses (user + date range), dashboard summary (user + type + month),
--         category breakdown (user + category), duplicate detection (user + date + amount),
--         recurring generation (user + source_recurring + date)
CREATE INDEX IF NOT EXISTS ix_expenses_user_type_spent ON expenses(user_id, expense_type, spent_at);
CREATE INDEX IF NOT EXISTS ix_expenses_user_category ON expenses(user_id, category_id);
CREATE INDEX IF NOT EXISTS ix_expenses_user_date_amount ON expenses(user_id, spent_at, amount);
CREATE INDEX IF NOT EXISTS ix_expenses_user_recurring_date ON expenses(user_id, source_recurring_id, spent_at);

-- Category table: lookup by user and uniqueness check by user+name
CREATE INDEX IF NOT EXISTS ix_categories_user_id ON categories(user_id);
CREATE INDEX IF NOT EXISTS ix_categories_user_name ON categories(user_id, name);

-- Recurring expenses: list active by user
CREATE INDEX IF NOT EXISTS ix_recurring_user_active ON recurring_expenses(user_id, active);

-- Bills: upcoming bills dashboard query (user + active + due date)
CREATE INDEX IF NOT EXISTS ix_bills_user_active_due ON bills(user_id, active, next_due_date);

-- Reminders: pending reminders scheduler query
CREATE INDEX IF NOT EXISTS ix_reminders_sent_send_at ON reminders(sent, send_at);

-- Ad impressions: time-range analytics queries
CREATE INDEX IF NOT EXISTS ix_ad_impressions_created ON ad_impressions(created_at);

-- User subscriptions: active subscription lookup
CREATE INDEX IF NOT EXISTS ix_user_subscriptions_user_active ON user_subscriptions(user_id, active);

-- Audit logs: user activity and time-range queries
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at);
