-- Migration 009: Client-Side Encryption setup storage
-- Issue #99
-- Apply with: psql $DATABASE_URL -f migrations/009_encryption_setup.sql

-- Adds the encryption_setup column to users.
-- Stores: kdf_salt (base64), kdf_iters, wrapped_dek (iv/ciphertext/tag),
-- algorithm tag.  The plaintext DEK and user password are NEVER stored.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS encryption_setup TEXT NULL;

-- Encrypted expense fields — client encrypts before sending, server stores
-- ciphertext.  hmac_tag allows the server to verify integrity before writing.
ALTER TABLE expenses
    ADD COLUMN IF NOT EXISTS encrypted_notes TEXT NULL,
    ADD COLUMN IF NOT EXISTS hmac_tag       VARCHAR(64) NULL;

-- NOTE: When encryption_setup is set for a user, the `notes` field in
-- expenses may be NULL and `encrypted_notes` carries the ciphertext instead.
-- The server never attempts to decrypt encrypted_notes — that is the client's
-- responsibility.
