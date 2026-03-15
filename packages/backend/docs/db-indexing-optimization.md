# Database Indexing Optimization

## Overview

Comprehensive database indexing strategy for FinMind's financial queries. Adds targeted indexes across all tables to improve performance of high-frequency operations including expense listing, category reports, bill reminders, and search.

## Index Summary

### Expenses Table (highest query volume)
| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_expenses_user_date` | user_id, spent_at | Primary listing — every page load |
| `idx_expenses_user_category_date` | user_id, category_id, spent_at | Category reports and filtering |
| `idx_expenses_user_date_amount` | user_id, spent_at, amount | SUM queries, monthly totals |
| `idx_expenses_notes_trgm` | notes (GIN trigram) | Full-text search on descriptions |
| `idx_expenses_user_type` | user_id, expense_type | Income vs expense filtering |
| `idx_expenses_source_recurring` | source_recurring_id (partial) | Recurring expense tracking |
| `idx_expenses_created` | created_at | Recent items sorting |

### Recurring Expenses
| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_recurring_user_active` | user_id, active | Active recurring listing |
| `idx_recurring_cadence` | cadence, start_date | Scheduling lookups |

### Bills
| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_bills_user_due` | user_id, next_due_date (partial) | Upcoming bills dashboard |
| `idx_bills_autopay` | user_id, autopay_enabled (partial) | Autopay bill filtering |

### Reminders
| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_reminders_pending` | send_at (partial) | Cron: find unsent reminders |
| `idx_reminders_user` | user_id, send_at | User reminder listing |
| `idx_reminders_bill` | bill_id (partial) | Bill-linked reminders |

### Categories
| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_categories_user` | user_id, name | Category lookup per user |

### Users
| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_users_email_lower` | LOWER(email) | Case-insensitive email lookup |

### Other Tables
| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_ad_impressions_placement_date` | placement, created_at | Analytics queries |
| `idx_ad_impressions_user` | user_id, created_at (partial) | User ad history |
| `idx_audit_user_date` | user_id, created_at | User audit trail |
| `idx_audit_action` | action, created_at | Action type filtering |
| `idx_user_subs_user_active` | user_id (partial) | Active subscriptions |
| `idx_user_subs_plan` | plan_id, active | Plan lookup |

## Performance Monitoring API

### GET `/admin/db/indexes`
List all indexes across application tables.

### GET `/admin/db/coverage`
Analyze index coverage for common query patterns.

**Response:**
```json
{
  "total_patterns": 9,
  "covered": 8,
  "missing": 1,
  "coverage_percentage": 88.9,
  "covered_patterns": [...],
  "missing_patterns": [...]
}
```

### GET `/admin/db/statistics`
Get row counts for all tables.

### POST `/admin/db/benchmark`
Run common query benchmarks with execution times.

## Implementation Details

### Partial Indexes
Several indexes use PostgreSQL partial indexes (`WHERE` clause) to reduce index size:
- `idx_bills_user_due` — only active bills
- `idx_reminders_pending` — only unsent reminders
- `idx_expenses_source_recurring` — only non-null values

### Trigram Index
The `idx_expenses_notes_trgm` uses PostgreSQL's `pg_trgm` extension for efficient `ILIKE` pattern matching on expense descriptions.

**Prerequisite:**
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### Column Order
Composite indexes follow the "equality → range → sort" principle:
- user_id first (equality filter)
- category_id or type next (equality filter)  
- date last (range/sort)

## Migration

```sql
-- Apply the migration
psql -d finmind -f app/db/026_indexing_optimization.sql
```

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_indexing.py -v
```

Covers index verification, coverage analysis, benchmarks, and API endpoints.
