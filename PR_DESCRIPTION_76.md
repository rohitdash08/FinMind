# PR: PII Export & Delete Workflow — GDPR-ready (Issue #76)

## Summary

Implements a fully GDPR-compliant Personal Data Export and Account Deletion workflow for FinMind users, along with an Admin Audit Log viewer. This PR closes Issue #76.

## Motivation

GDPR (EU) and similar privacy regulations (CCPA, PDPA) require that products:
1. Allow users to export a copy of all their personal data on request.
2. Allow users to permanently and irreversibly delete all their data.
3. Maintain an auditable trail of data-access and deletion events.

## Changes

### New files

| File | Purpose |
|------|---------|
| `packages/backend/app/services/pii_service.py` | Core business logic for PII export and permanent deletion |
| `packages/backend/app/routes/user.py` | User self-service endpoints (`/api/user/export`, `/api/user/account`) |
| `packages/backend/app/routes/admin.py` | Admin audit log endpoint (`/api/admin/audit-log`) |

### Modified files

| File | Change |
|------|--------|
| `packages/backend/app/routes/__init__.py` | Register `user_bp` and `admin_bp` blueprints |
| `packages/backend/app/models.py` | Added `details`, `ip_address`, `user_agent` columns to `AuditLog` |
| `packages/backend/app/db/schema.sql` | Updated `audit_logs` DDL + `ALTER TABLE` migration stanzas + indexes |
| `packages/backend/app/services/audit.py` | New audit service (was untracked; now committed) |

## API Endpoints

### `GET /api/user/export`

Returns a complete JSON package of all personal data belonging to the authenticated user.

**Auth:** JWT Bearer token required.

**Response `200`:**
```json
{
  "export_generated_at": "2024-05-01T12:00:00Z",
  "profile": { "id": 1, "email": "user@example.com", ... },
  "categories": [...],
  "expenses": [...],
  "recurring_expenses": [...],
  "bills": [...],
  "reminders": [...],
  "subscriptions": [...],
  "ad_impressions": [...],
  "audit_trail": [...]
}
```

An `AuditLog` entry with `action="pii_export"` is written on every successful export, including the client IP and User-Agent.

---

### `DELETE /api/user/account`

Permanently and **irreversibly** deletes the authenticated user's account and all associated data.

**Auth:** JWT Bearer token required.

**Request body:**
```json
{
  "confirm": "DELETE_MY_ACCOUNT",
  "reason": "optional free-text reason"
}
```

The `confirm` field must equal the literal string `"DELETE_MY_ACCOUNT"` to prevent accidental deletion.

**Deletion order (FK-safe):**
1. `reminders`
2. `bills`
3. `expenses`
4. `recurring_expenses`
5. `categories`
6. `user_subscriptions`
7. `ad_impressions`
8. `audit_logs.user_id` → set to `NULL` (audit trail preserved, PII de-linked)
9. `users` row deleted

**Response `200`:**
```json
{
  "message": "account and all associated data permanently deleted",
  "deleted_counts": {
    "reminders": 3,
    "bills": 2,
    "expenses": 47,
    "recurring_expenses": 1,
    "categories": 5,
    "subscriptions": 1,
    "ad_impressions": 120,
    "audit_logs_anonymised": 4
  }
}
```

Two `AuditLog` entries are written:
- `account_deletion_initiated` — before deletion, with user email and reason.
- `account_deletion_completed` — after deletion, with `user_id=NULL` (tombstone).

---

### `GET /api/admin/audit-log`

Returns a paginated list of all audit log entries. **Admin role required.**

**Auth:** JWT Bearer token required (caller must have `role="ADMIN"`).

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `user_id` | int | Filter by user |
| `action` | string | Filter by action (exact) |
| `start_date` | ISO-8601 | Filter from date |
| `end_date` | ISO-8601 | Filter to date |
| `page` | int | Page number (default: 1) |
| `page_size` | int | Results per page (default: 50, max: 200) |

**Response `200`:**
```json
{
  "total": 42,
  "page": 1,
  "page_size": 50,
  "pages": 1,
  "entries": [
    {
      "id": 99,
      "user_id": 7,
      "action": "pii_export",
      "details": { "email": "user@example.com" },
      "ip_address": "203.0.113.5",
      "user_agent": "Mozilla/5.0 ...",
      "created_at": "2024-05-01T12:00:00Z"
    }
  ]
}
```

## Security Considerations

- All endpoints are protected with `@jwt_required()`.
- Account deletion requires an explicit confirmation string — prevents accidental data loss.
- Admin audit log is gated behind an `ADMIN` role check at the application layer.
- Audit entries for deletion use `user_id=NULL` after account removal, preserving the trail without re-linking PII.
- Client IP is extracted respecting `X-Forwarded-For` (proxy-aware).

## Database Migration

The `audit_logs` table gains three new nullable columns. The schema.sql file includes idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` stanzas, safe to run on existing databases.

```sql
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS details JSONB;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_agent VARCHAR(500);
```

## Testing

Manual smoke-test flow:

```bash
# 1. Register & login
curl -s -X POST /auth/register -d '{"email":"gdpr@test.com","password":"test1234"}'
TOKEN=$(curl -s -X POST /auth/login -d '{"email":"gdpr@test.com","password":"test1234"}' | jq -r .access_token)

# 2. Export data
curl -s -H "Authorization: Bearer $TOKEN" /api/user/export | jq .

# 3. Delete account
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  -d '{"confirm":"DELETE_MY_ACCOUNT","reason":"testing"}' \
  /api/user/account | jq .

# 4. Admin audit log (requires ADMIN role)
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "/api/admin/audit-log?action=account_deletion_completed" | jq .
```

## Checklist

- [x] `GET /api/user/export` — returns full PII package as JSON
- [x] `DELETE /api/user/account` — irreversible deletion with confirmation guard
- [x] `GET /api/admin/audit-log` — paginated, filterable, admin-only
- [x] Audit trail written for every export and deletion event
- [x] `AuditLog` model updated with `details`, `ip_address`, `user_agent`
- [x] `db/schema.sql` updated with migration stanzas and indexes
- [x] Deletion preserves anonymised audit trail (GDPR Art. 17 balancing test)
- [x] No plaintext secrets or PII in logs
- [x] Proxy-aware IP extraction (`X-Forwarded-For`)

## References

- [GDPR Article 15 — Right of access](https://gdpr-info.eu/art-15-gdpr/)
- [GDPR Article 17 — Right to erasure](https://gdpr-info.eu/art-17-gdpr/)
- Closes #76
