# GDPR PII Export & Delete Workflow

GDPR-compliant personal data export and irreversible account deletion with full audit trail.

## Overview

This feature implements three core GDPR requirements:

1. **Right of Access (Article 15)** – Users can export all their personal data in a structured JSON format
2. **Right to Erasure (Article 17)** – Users can request permanent deletion of their account and all associated data
3. **Accountability (Article 5(2))** – All export and deletion actions are recorded in an immutable audit trail

## Architecture

```
User Request → API Route → GDPR Service → Database
                                ↓
                        GDPR Audit Log (immutable)
```

### Deletion Lifecycle

```
PENDING → CONFIRMED → (grace period) → PROCESSING → COMPLETED
   ↓          ↓
CANCELLED  CANCELLED
```

- **Grace period**: 7 days (configurable via `DeletionRequest.GRACE_PERIOD_DAYS`)
- **Confirmation**: Token-based (cryptographically random, 64 chars)
- **Hard delete**: Cascades across all user tables, soft-deletes the User row

## API Endpoints

All endpoints require JWT authentication (`Authorization: Bearer <token>`).

### PII Export

```
POST /gdpr/export
```

Returns a JSON package containing all user data across every table:
- Profile (email, currency, role, timestamps)
- Categories, Expenses, Recurring Expenses
- Bills, Reminders
- Subscriptions, Ad Impressions
- Audit Logs

Password hashes are **never** included in the export.

**Response** `200`:
```json
{
  "export": {
    "export_generated_at": "2025-01-15T12:00:00",
    "user_id": 1,
    "profile": { "email": "user@example.com", ... },
    "categories": [...],
    "expenses": [...],
    ...
  }
}
```

### Request Deletion

```
POST /gdpr/delete
Content-Type: application/json

{ "reason": "optional reason" }
```

**Response** `201`:
```json
{
  "message": "deletion requested",
  "request_id": 1,
  "confirmation_token": "abc123...",
  "grace_period_ends_at": "2025-01-22T12:00:00"
}
```

### Confirm Deletion

```
POST /gdpr/delete/confirm
Content-Type: application/json

{ "confirmation_token": "abc123..." }
```

### Cancel Deletion

```
POST /gdpr/delete/cancel
```

Works for both PENDING and CONFIRMED states. Users can re-request after cancelling.

### Check Deletion Status

```
GET /gdpr/delete/status
```

### Execute Deletion (Admin Only)

```
POST /gdpr/delete/execute/<user_id>
```

Only executes if:
- Request is in CONFIRMED state
- Grace period has elapsed
- Caller has ADMIN role

### View Audit Trail (Admin Only)

```
GET /gdpr/audit?page=1&per_page=50&user_id=123
```

Paginated, filterable by user_id.

## Database Changes

### New Tables

- `gdpr_audit_logs` – Immutable compliance audit trail (never deleted)
- `deletion_requests` – Tracks deletion lifecycle with confirmation tokens

### Modified Tables

- `users` – Added `is_deleted` (boolean) and `deleted_at` (timestamp)

### Migration

```bash
psql -U $DB_USER -d finmind -f app/db/004_gdpr_pii.sql
```

## Data Handling

### What Gets Deleted

| Table | Action |
|-------|--------|
| expenses | Hard delete |
| recurring_expenses | Hard delete |
| categories | Hard delete |
| bills | Hard delete |
| reminders | Hard delete |
| ad_impressions | Hard delete |
| user_subscriptions | Hard delete |
| audit_logs | Hard delete |
| deletion_requests | Hard delete |
| users | Soft delete (email anonymized, password redacted) |

### What Gets Preserved

- `gdpr_audit_logs` – Retained for 7 years per GDPR Article 17(3)(e)
- User row (anonymized) – Preserves referential integrity

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_gdpr.py -v
```

19 tests covering:
- PII export completeness and audit logging
- Deletion request/confirm/cancel lifecycle
- Grace period enforcement
- Duplicate deletion prevention
- Admin-only access controls
- Audit trail immutability after deletion

## Files Changed

| File | Change |
|------|--------|
| `app/models.py` | Added `GDPRAuditLog`, `DeletionRequest`, `GDPRAction`, `DeletionStatus` models; `is_deleted`/`deleted_at` on User |
| `app/services/gdpr.py` | **New** – PII export, deletion workflow, audit logging |
| `app/routes/gdpr.py` | **New** – 7 REST endpoints |
| `app/routes/__init__.py` | Registered `gdpr` blueprint |
| `app/db/004_gdpr_pii.sql` | **New** – Migration for GDPR tables |
| `tests/conftest.py` | Added fakeredis autouse fixture |
| `tests/test_gdpr.py` | **New** – 19 comprehensive tests |
| `docs/gdpr-pii-export-delete.md` | **New** – This documentation |
