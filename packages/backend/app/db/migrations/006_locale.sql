-- Migration 006: Locale-aware formatting — add preferred_locale to users
-- Issue #131

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS preferred_locale VARCHAR(20) NOT NULL DEFAULT 'en_IN';
