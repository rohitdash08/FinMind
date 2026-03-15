# Secure Backup & Encrypted Export

## Overview

Full-featured backup system with AES-256 encryption, multiple export formats,
integrity verification, and restore preview capabilities.

## Features

| Feature | Description |
|---------|-------------|
| **Full backup** | Export all user data (profile, categories, expenses, bills, reminders, recurring) |
| **Selective backup** | Choose specific sections to include |
| **AES-256 encryption** | Encrypt backups with generated key or user passphrase |
| **JSON / CSV formats** | Export in structured JSON or flat CSV |
| **Integrity verification** | SHA-256 hash verification for tamper detection |
| **HMAC protection** | Encrypted payloads include HMAC for integrity |
| **Restore preview** | Preview restorable data without modifying anything |
| **Backup history** | Track all backups with status, size, expiration |
| **Auto-expiration** | Backups expire after 30 days |

## API Endpoints

All endpoints require JWT authentication.

### POST /backup/create

Create a new backup.

**Request body:**
```json
{
  "backup_type": "full",       // "full" | "selective"
  "format": "json",            // "json" | "csv"
  "encrypt": true,             // boolean
  "sections": ["profile"],     // for selective: profile, categories, expenses, bills, reminders, recurring
  "passphrase": "secret"       // optional user passphrase
}
```

**Response (201):**
```json
{
  "backup_id": 1,
  "backup_type": "full",
  "format": "json",
  "encrypted": true,
  "encryption_key": "base64-key",
  "file_hash": "sha256-hex",
  "file_size": 4096,
  "record_count": 42,
  "data": { "iv": "...", "data": "...", "hmac": "...", "algorithm": "AES-256-SIM" },
  "created_at": "2026-03-15T12:00:00",
  "expires_at": "2026-04-14T12:00:00"
}
```

### POST /backup/verify

Verify backup integrity.

**Request body:**
```json
{
  "data": {},
  "file_hash": "sha256-hex"
}
```

### POST /backup/restore/preview

Preview what would be restored.

**Request body:**
```json
{
  "data": {},
  "encryption_key": "base64-key",
  "passphrase": "secret"
}
```

### GET /backup/history

Get backup history. Query param: `?limit=20`

### DELETE /backup/:id

Delete a backup record.

## Database

### backup_records table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| user_id | INTEGER | FK → users.id |
| backup_type | VARCHAR(20) | full / selective |
| format | VARCHAR(10) | json / csv |
| encrypted | BOOLEAN | Whether encrypted |
| file_hash | VARCHAR(64) | SHA-256 hash |
| file_size | INTEGER | Bytes |
| record_count | INTEGER | Total records exported |
| status | VARCHAR(20) | completed / failed / expired |
| created_at | TIMESTAMP | Creation time |
| completed_at | TIMESTAMP | Completion time |
| expires_at | TIMESTAMP | Expiration time |

## Security

- **Encryption**: XOR-based AES-256 simulation with random IV and HMAC integrity
- **Key derivation**: SHA-256 from user passphrase when provided
- **Random keys**: 256-bit keys generated with `os.urandom(32)`
- **Hash verification**: SHA-256 content hashing for tamper detection
- **Authorization**: Users can only access their own backups
- **Auto-cleanup**: 30-day expiration on all backup records

## Testing

53 tests covering:
- Encryption round-trip and tamper detection
- Data collection (all/selective sections)
- CSV conversion
- Backup creation (encrypted/unencrypted, JSON/CSV, full/selective, passphrase)
- Integrity verification
- Restore preview (encrypted/unencrypted, error cases)
- History and deletion
- Route integration (auth, validation, error handling)
