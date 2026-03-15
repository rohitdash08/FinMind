-- Transaction Deduplication Intelligence
-- Adds dedup tracking table and fingerprint column to expenses

ALTER TABLE expenses
ADD COLUMN fingerprint VARCHAR(64) DEFAULT NULL;

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    fingerprint VARCHAR(64) NOT NULL,
    expense_ids TEXT DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
    master_expense_id INTEGER REFERENCES expenses(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_fingerprint ON expenses(fingerprint);
CREATE INDEX IF NOT EXISTS idx_duplicate_groups_user ON duplicate_groups(user_id, status);
CREATE INDEX IF NOT EXISTS idx_duplicate_groups_fingerprint ON duplicate_groups(user_id, fingerprint);
