# Database Indexes — Issue #128

## Overview

This document describes the composite indexes added to the FinMind database
to improve query performance for the most common access patterns.

## Indexes Added

### expenses

| Index Name | Columns | Benefits |
|---|---|---|
| `ix_expenses_user_spent_at` | `(user_id, spent_at)` | List expenses for a user within a date range. Covers the primary expense listing query and sorted retrieval by `spent_at DESC`. |
| `ix_expenses_user_category` | `(user_id, category_id)` | Filter expenses by user and category. Used when displaying category-specific expense views. |
| `ix_expenses_user_type_spent` | `(user_id, expense_type, spent_at)` | Dashboard summary query that filters by user, groups by expense type (INCOME vs EXPENSE), and extracts year/month from `spent_at`. |

### bills

| Index Name | Columns | Benefits |
|---|---|---|
| `ix_bills_user_due` | `(user_id, next_due_date)` | Upcoming bills query: fetch active bills for a user sorted by due date. |
| `ix_bills_user_active` | `(user_id, active)` | Filter bills by active status for a given user. |

### reminders

| Index Name | Columns | Benefits |
|---|---|---|
| `ix_reminders_user_send_at` | `(user_id, send_at)` | Fetch reminders for a user ordered by send time. |
| `ix_reminders_pending` | `(user_id, sent, send_at)` | Background reminder dispatch: find unsent reminders for a user, ordered by send_at. |

### categories

| Index Name | Columns | Benefits |
|---|---|---|
| `ix_categories_user` | `(user_id)` | List categories for a user. Simple single-column index. |

### recurring_expenses

| Index Name | Columns | Benefits |
|---|---|---|
| `ix_recurring_user_active` | `(user_id, active)` | Fetch active recurring expenses for a user. Used by the recurring expense scheduler. |

### background_jobs

| Index Name | Columns | Benefits |
|---|---|---|
| `ix_bg_jobs_status_retry` | `(status, next_retry_at)` | Job runner poll query: find pending or retry-ready jobs. |
| `ix_bg_jobs_type` | `(job_type)` | Filter jobs by type for monitoring and debugging. |

## How to Apply Indexes

### New Deployments

Indexes are created automatically when `db.create_all()` runs because they are
declared in `__table_args__` on each SQLAlchemy model. No manual steps required.

### Existing Deployments (PostgreSQL)

Run the migration script:

```bash
cd packages/backend
python scripts/add_indexes.py
```

This uses `CREATE INDEX IF NOT EXISTS`, so it is safe to run multiple times.

Alternatively, the `_ensure_schema_compatibility()` function in `app/__init__.py`
creates these indexes automatically on every application startup (PostgreSQL only).

### Manual Application

If you need to apply indexes manually against a PostgreSQL database:

```sql
CREATE INDEX IF NOT EXISTS ix_expenses_user_spent_at ON expenses (user_id, spent_at);
CREATE INDEX IF NOT EXISTS ix_expenses_user_category ON expenses (user_id, category_id);
CREATE INDEX IF NOT EXISTS ix_expenses_user_type_spent ON expenses (user_id, expense_type, spent_at);
CREATE INDEX IF NOT EXISTS ix_bills_user_due ON bills (user_id, next_due_date);
CREATE INDEX IF NOT EXISTS ix_bills_user_active ON bills (user_id, active);
CREATE INDEX IF NOT EXISTS ix_reminders_user_send_at ON reminders (user_id, send_at);
CREATE INDEX IF NOT EXISTS ix_reminders_pending ON reminders (user_id, sent, send_at);
CREATE INDEX IF NOT EXISTS ix_categories_user ON categories (user_id);
CREATE INDEX IF NOT EXISTS ix_recurring_user_active ON recurring_expenses (user_id, active);
CREATE INDEX IF NOT EXISTS ix_bg_jobs_status_retry ON background_jobs (status, next_retry_at);
CREATE INDEX IF NOT EXISTS ix_bg_jobs_type ON background_jobs (job_type);
```

## Performance Impact

- **Write overhead**: Each additional index adds a small overhead to INSERT and
  UPDATE operations because the index must be maintained. For FinMind's workload
  (mostly reads), this trade-off is well worthwhile.
- **Storage**: Composite indexes consume additional disk space. The total
  additional storage is minimal for typical FinMind data volumes.
- **Query improvement**: Queries that filter on the indexed columns will see
  significant improvement, especially as the dataset grows. The `expenses` table
  is typically the largest and benefits the most.
- **No downtime**: `CREATE INDEX IF NOT EXISTS` is a non-blocking operation in
  PostgreSQL for existing indexes. New index creation may briefly lock the table
  for large datasets; consider `CREATE INDEX CONCURRENTLY` for zero-downtime
  migrations on large production databases.
