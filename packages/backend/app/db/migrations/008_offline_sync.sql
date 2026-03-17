-- Migration 008: Offline-First Sync with Conflict Resolution
-- Issue #98
-- Apply with: psql $DATABASE_URL -f migrations/008_offline_sync.sql

-- Offline transaction queue: stores operations created while the client
-- was offline.  Each row represents one pending mutation (create/update/delete)
-- against a resource (expense, bill, category, etc.).
CREATE TABLE IF NOT EXISTS sync_queue (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id       VARCHAR(64)   NOT NULL,           -- opaque device/client identifier
    operation       VARCHAR(10)   NOT NULL,            -- CREATE | UPDATE | DELETE
    resource_type   VARCHAR(50)   NOT NULL,            -- expense | bill | category | ...
    resource_id     INTEGER       NULL,                -- NULL for CREATE (not yet assigned)
    payload         JSONB         NOT NULL DEFAULT '{}',
    client_seq      BIGINT        NOT NULL,            -- client-side monotonic sequence number
    client_ts       TIMESTAMPTZ   NOT NULL,            -- timestamp on client when op was recorded
    status          VARCHAR(20)   NOT NULL DEFAULT 'pending',
                                                       -- pending | applied | conflict | error
    conflict_info   JSONB         NULL,                -- populated when status = 'conflict'
    server_id       INTEGER       NULL,                -- server-assigned id after CREATE is applied
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    applied_at      TIMESTAMPTZ   NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_queue_user_status
    ON sync_queue (user_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_sync_queue_client
    ON sync_queue (user_id, client_id, client_seq);

-- Sync checkpoint: records the last server-side sequence number acknowledged
-- by each client so incremental pulls only return new data.
CREATE TABLE IF NOT EXISTS sync_checkpoints (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id   VARCHAR(64)   NOT NULL,
    last_seq    BIGINT        NOT NULL DEFAULT 0,   -- last server_seq delivered to this client
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, client_id)
);

-- Add server_seq to expenses for incremental pull detection.
-- A server_seq is assigned on every INSERT or UPDATE so clients can
-- ask "give me everything newer than seq N".
ALTER TABLE expenses
    ADD COLUMN IF NOT EXISTS server_seq BIGSERIAL;

CREATE INDEX IF NOT EXISTS idx_expenses_user_server_seq
    ON expenses (user_id, server_seq);
