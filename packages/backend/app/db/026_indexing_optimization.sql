-- Migration: Database indexing optimization for financial queries
-- Issue: #128
-- Improves performance of high-frequency queries with targeted indexes

-- ═══════════════════════════════════════════════════════════════════════
-- EXPENSES TABLE INDEXES
-- Most queried table: date range, category, search, pagination
-- ═══════════════════════════════════════════════════════════════════════

-- Primary lookup: user + date range (used by list, insights, reports)
CREATE INDEX IF NOT EXISTS idx_expenses_user_date
    ON expenses(user_id, spent_at DESC);

-- Category filtering: user + category + date (used by category reports)
CREATE INDEX IF NOT EXISTS idx_expenses_user_category_date
    ON expenses(user_id, category_id, spent_at DESC);

-- Amount aggregation: user + date + amount (SUM queries, monthly totals)
CREATE INDEX IF NOT EXISTS idx_expenses_user_date_amount
    ON expenses(user_id, spent_at, amount);

-- Full-text search on notes (used by search endpoint)
CREATE INDEX IF NOT EXISTS idx_expenses_notes_trgm
    ON expenses USING gin (notes gin_trgm_ops);

-- Type filtering: expense vs income
CREATE INDEX IF NOT EXISTS idx_expenses_user_type
    ON expenses(user_id, expense_type);

-- Source recurring lookup
CREATE INDEX IF NOT EXISTS idx_expenses_source_recurring
    ON expenses(source_recurring_id)
    WHERE source_recurring_id IS NOT NULL;

-- Created at for recent items
CREATE INDEX IF NOT EXISTS idx_expenses_created
    ON expenses(created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════
-- RECURRING EXPENSES TABLE INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- Active recurring expenses per user
CREATE INDEX IF NOT EXISTS idx_recurring_user_active
    ON recurring_expenses(user_id, active)
    WHERE active = true;

-- Cadence lookup for scheduling
CREATE INDEX IF NOT EXISTS idx_recurring_cadence
    ON recurring_expenses(cadence, start_date);


-- ═══════════════════════════════════════════════════════════════════════
-- BILLS TABLE INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- Upcoming bills per user (dashboard, reminders)
CREATE INDEX IF NOT EXISTS idx_bills_user_due
    ON bills(user_id, next_due_date)
    WHERE active = true;

-- Autopay bills
CREATE INDEX IF NOT EXISTS idx_bills_autopay
    ON bills(user_id, autopay_enabled)
    WHERE active = true AND autopay_enabled = true;


-- ═══════════════════════════════════════════════════════════════════════
-- REMINDERS TABLE INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- Pending reminders to send (cron job: unsent, ordered by send time)
CREATE INDEX IF NOT EXISTS idx_reminders_pending
    ON reminders(send_at)
    WHERE sent = false;

-- User reminders lookup
CREATE INDEX IF NOT EXISTS idx_reminders_user
    ON reminders(user_id, send_at DESC);

-- Bill-linked reminders
CREATE INDEX IF NOT EXISTS idx_reminders_bill
    ON reminders(bill_id)
    WHERE bill_id IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════════
-- CATEGORIES TABLE INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- Category lookup per user
CREATE INDEX IF NOT EXISTS idx_categories_user
    ON categories(user_id, name);


-- ═══════════════════════════════════════════════════════════════════════
-- USERS TABLE INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- Email lookup is already unique but add a functional index for case-insensitive
CREATE INDEX IF NOT EXISTS idx_users_email_lower
    ON users(LOWER(email));


-- ═══════════════════════════════════════════════════════════════════════
-- AD IMPRESSIONS TABLE INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- Analytics: placement + date range
CREATE INDEX IF NOT EXISTS idx_ad_impressions_placement_date
    ON ad_impressions(placement, created_at DESC);

-- User ad history
CREATE INDEX IF NOT EXISTS idx_ad_impressions_user
    ON ad_impressions(user_id, created_at DESC)
    WHERE user_id IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════════
-- AUDIT LOGS TABLE INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- User audit trail
CREATE INDEX IF NOT EXISTS idx_audit_user_date
    ON audit_logs(user_id, created_at DESC);

-- Action type filtering
CREATE INDEX IF NOT EXISTS idx_audit_action
    ON audit_logs(action, created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════
-- SUBSCRIPTION PLANS & USER SUBSCRIPTIONS INDEXES
-- ═══════════════════════════════════════════════════════════════════════

-- Active user subscriptions
CREATE INDEX IF NOT EXISTS idx_user_subs_user_active
    ON user_subscriptions(user_id)
    WHERE active = true;

-- Plan lookup
CREATE INDEX IF NOT EXISTS idx_user_subs_plan
    ON user_subscriptions(plan_id, active);


-- ═══════════════════════════════════════════════════════════════════════
-- EXTENSION REQUIREMENT
-- Required for trigram index on expenses.notes
-- ═══════════════════════════════════════════════════════════════════════
-- Note: Run this before applying the migration if not already installed:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
