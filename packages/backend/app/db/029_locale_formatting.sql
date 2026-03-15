-- Migration: Add locale preferences to users table
-- Issue: #131 - Locale-aware date, currency & number formatting

ALTER TABLE users ADD COLUMN locale VARCHAR(10) DEFAULT 'en_US' NOT NULL;
ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC' NOT NULL;
ALTER TABLE users ADD COLUMN date_format VARCHAR(20) DEFAULT 'YYYY-MM-DD' NOT NULL;
ALTER TABLE users ADD COLUMN number_format VARCHAR(20) DEFAULT 'standard' NOT NULL;
ALTER TABLE users ADD COLUMN currency_display VARCHAR(20) DEFAULT 'symbol' NOT NULL;

-- Index for locale-based queries
CREATE INDEX idx_users_locale ON users(locale);
