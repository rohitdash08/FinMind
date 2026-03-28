# GDPR PII Export & Delete Workflow

This implementation provides full GDPR compliance for FinMind users, enabling them to exercise their Right to Access and Right to be Forgotten.

## Features

### 1. Data Export (`/api/gdpr/export`)
- **ZIP Download**: Complete user data export as a downloadable ZIP file
- **Structured JSON**: All data exported in clean, readable JSON format
- **Comprehensive Coverage**: Exports all user-related data across all tables
- **Export Preview**: Preview what will be exported before downloading

### 2. Data Deletion (`/api/gdpr/delete`)
- **Right to be Forgotten**: Permanently delete all user PII
- **Safety Confirmation**: Requires explicit confirmation token
- **Cascade Deletion**: Properly handles foreign key relationships
- **Deletion Preview**: See exactly what will be deleted
- **Irreversible**: Once deleted, data cannot be recovered

### 3. Audit Trail
- **Complete Logging**: All GDPR actions logged with timestamps
- **Non-Repudiation**: Cannot deny or dispute logged actions
- **Compliance Ready**: Meets regulatory audit requirements

## API Endpoints

### Public
- `GET /api/gdpr/info` - Information about GDPR rights

### Authenticated (requires Bearer token)
- `GET /api/gdpr/export` - Download all personal data (ZIP)
- `GET /api/gdpr/export/preview` - Preview export contents
- `POST /api/gdpr/delete` - Delete all personal data
- `GET /api/gdpr/delete/preview` - Preview deletion impact
- `GET /api/gdpr/audit-log` - View GDPR audit history

## Usage Examples

### Export Your Data
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://api.finmind.app/gdpr/export \
     --output my_data.zip
```

### Preview Before Export
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://api.finmind.app/gdpr/export/preview
```

### Delete Your Account
```bash
curl -X POST \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"confirmation_token":"DELETE_MY_DATA_PERMANENTLY"}' \
     https://api.finmind.app/gdpr/delete
```

### Preview Before Deletion
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://api.finmind.app/gdpr/delete/preview
```

## Data Exported

The export includes:
- User profile (email, currency preference, role)
- Categories
- Expenses (regular and recurring)
- Bills and reminders
- Ad impressions
- Subscription history
- Audit logs

## Security Considerations

1. **Authentication Required**: All data access requires valid JWT token
2. **Confirmation Token**: Deletion requires explicit confirmation to prevent accidents
3. **Audit Logging**: All actions logged for compliance
4. **Cascade Delete**: Related data properly cleaned up
5. **Anonymized Audit**: Post-deletion, audit logs retain action record but anonymize user_id

## Testing

Run the GDPR test suite:
```bash
cd packages/backend
pytest tests/test_gdpr.py -v
```

Tests cover:
- Export functionality
- Deletion with confirmation
- Audit logging
- Preview endpoints
- Full integration workflow

## GDPR Compliance Notes

### Right to Access (Article 15)
✅ Users can download all their personal data in a structured format

### Right to Erasure (Article 17)
✅ Users can permanently delete their account and all data

### Data Portability (Article 20)
✅ Data exported in machine-readable JSON format

### Records of Processing (Article 30)
✅ All GDPR actions logged with audit trail

## Implementation Details

### Files Added/Modified

**New Files:**
- `packages/backend/app/routes/gdpr.py` - Main GDPR route handlers
- `packages/backend/tests/test_gdpr.py` - Comprehensive test suite

**Modified Files:**
- `packages/backend/app/routes/__init__.py` - Register GDPR blueprint
- `packages/backend/app/routes/auth.py` - Add `verify_token` helper
- `packages/backend/app/openapi.yaml` - API documentation

### Database Impact

No schema changes required. Uses existing tables:
- `users` - User account data
- `categories` - User categories
- `expenses` - User expenses
- `recurring_expenses` - Recurring expense definitions
- `bills` - User bills
- `reminders` - User reminders
- `ad_impressions` - Ad interaction data
- `user_subscriptions` - Subscription data
- `audit_logs` - Action audit trail

### Deletion Order

To respect foreign key constraints:
1. Expenses (child of users, categories)
2. RecurringExpenses (child of users, categories)
3. Reminders (child of users, bills)
4. Bills (child of users)
5. Categories (child of users)
6. AdImpressions (child of users)
7. UserSubscriptions (child of users)
8. AuditLogs (anonymized, not deleted)
9. Users (final deletion)

## Acceptance Criteria Met

- [x] Export package generation (ZIP with JSON)
- [x] Irreversible deletion workflow
- [x] Audit trail logging (all actions logged)
- [x] Production-ready implementation
- [x] Comprehensive test coverage
- [x] Documentation updated (OpenAPI spec)

## Bounty Information

This implementation addresses FinMind Issue #76:
**PII Export & Delete Workflow (GDPR-ready) - $500 Bounty**

- Implements complete GDPR compliance features
- Production-ready code with error handling
- Full test coverage
- API documentation included
