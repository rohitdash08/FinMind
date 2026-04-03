# Backup & Encrypted Export

Issue: [#126](https://github.com/FinMind/FinMind/issues/126) — Secure backup & encrypted export options.

## Overview

FinMind supports encrypted backup and restore of user data. All exports are encrypted client-side with a user-provided backup password using AES-256-GCM with PBKDF2 key derivation. The server never stores the backup password.

## Encryption Details

| Parameter | Value |
|-----------|-------|
| Cipher | AES-256-GCM |
| Key Derivation | PBKDF2-HMAC-SHA256 |
| Iterations | 600,000 |
| Salt | 16 bytes (random per export) |
| Nonce | 12 bytes (random per export) |
| Key Length | 256 bits |

Each export produces a unique ciphertext even for identical data because the salt and nonce are randomly generated.

## API Endpoints

All endpoints require JWT authentication (`Authorization: Bearer <token>`).

### POST `/backup/export`

Export all user data (categories, expenses, recurring expenses, bills) as encrypted JSON.

**Request body:**

```json
{
  "backup_password": "your-secure-backup-password"
}
```

**Response (`200`):**

```json
{
  "backup": {
    "version": 1,
    "salt": "<base64>",
    "nonce": "<base64>",
    "ciphertext": "<base64>",
    "kdf": "pbkdf2-sha256",
    "kdf_iterations": 600000,
    "cipher": "aes-256-gcm"
  }
}
```

### POST `/backup/export/csv`

Export expenses only as encrypted CSV. Same request/response format as `/backup/export`.

The decrypted payload is a CSV file with columns: `id, amount, currency, expense_type, category_id, description, date`.

### POST `/backup/import`

Import and decrypt a previously exported JSON backup. Merges data intelligently:

- **Categories**: matched by name; existing categories are reused, new ones are created.
- **Expenses**: deduplicated by (date, amount, description); duplicates are skipped.

**Request body:**

```json
{
  "backup_password": "the-password-used-during-export",
  "backup": {
    "version": 1,
    "salt": "<base64>",
    "nonce": "<base64>",
    "ciphertext": "<base64>",
    "kdf": "pbkdf2-sha256",
    "kdf_iterations": 600000,
    "cipher": "aes-256-gcm"
  }
}
```

**Response (`200`):**

```json
{
  "imported_categories": 2,
  "imported_expenses": 15,
  "skipped_duplicates": 3
}
```

### GET `/backup/history`

List past backup operations for the authenticated user.

**Response (`200`):**

```json
[
  {
    "id": 2,
    "format": "csv",
    "record_count": 42,
    "created_at": "2026-03-15T10:30:00"
  },
  {
    "id": 1,
    "format": "json",
    "record_count": 42,
    "created_at": "2026-03-14T09:00:00"
  }
]
```

## Error Responses

| Status | Condition |
|--------|-----------|
| `400` | Missing or short password (min 8 chars) |
| `400` | Wrong password during import |
| `400` | Malformed backup envelope |
| `400` | Decrypted data is not valid JSON |
| `401` | Missing or invalid JWT token |

## Security Considerations

- The backup password is never stored on the server. If the user loses it, the backup cannot be decrypted.
- Each export uses a fresh random salt and nonce, so identical data produces different ciphertexts.
- PBKDF2 with 600,000 iterations provides resistance against brute-force attacks on the backup password.
- AES-256-GCM provides both confidentiality and integrity (authenticated encryption).
- Passwords must be at least 8 characters long.

## Dependencies

- `cryptography` Python package (added to `requirements.txt`)
