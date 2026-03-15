# Transaction Deduplication Intelligence

## Overview

Intelligent duplicate detection across imports and syncs using fingerprint-based
matching with configurable similarity thresholds. Supports exact and fuzzy
matching, group review, and multiple resolution strategies.

Resolves: [#113](https://github.com/rohitdash08/FinMind/issues/113)

## Features

- **Fingerprint-based detection** — SHA-256 hash of normalized transaction attributes
- **Exact matching** — Same amount, currency, date, and notes
- **Fuzzy matching** — Configurable date window and amount tolerance
- **Text normalization** — Strips references, collapses whitespace, case-insensitive
- **Group management** — Track, review, and resolve duplicate groups
- **Multiple resolution strategies** — Keep one, keep all, merge, or ignore
- **Coverage statistics** — Track fingerprinting progress and resolution status

## Detection Logic

### Fingerprint Computation

Each expense gets a 16-character fingerprint hash based on:
- Amount (2 decimal precision)
- Currency (uppercase)
- Date (ISO format)
- Notes (normalized)
- Category ID (optional)

### Fuzzy Matching

When enabled, also checks for:
- Same amount + currency on nearby dates (configurable window)
- Notes are normalized: lowercased, whitespace collapsed, reference numbers stripped

## API Endpoints

### `POST /dedup/scan`

Scan expenses for potential duplicates.

**Body (optional):**
```json
{
  "date_window": 1,       // Days window for fuzzy matching (0-30, default: 1)
  "amount_tolerance": 0   // Amount tolerance (default: 0)
}
```

**Response:**
```json
{
  "scanned": 156,
  "duplicate_groups": 5,
  "new_groups": 3,
  "potential_duplicates": 12
}
```

### `GET /dedup/groups`

List duplicate groups with matching expenses.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter: PENDING, RESOLVED, IGNORED |

**Response:**
```json
{
  "groups": [
    {
      "id": 1,
      "fingerprint": "a1b2c3d4e5f67890",
      "status": "PENDING",
      "master_expense_id": null,
      "expenses": [
        {"id": 10, "amount": 5.00, "notes": "Coffee", "spent_at": "2024-06-15"},
        {"id": 15, "amount": 5.00, "notes": "Coffee", "spent_at": "2024-06-15"}
      ],
      "count": 2
    }
  ],
  "count": 1
}
```

### `POST /dedup/groups/<id>/resolve`

Resolve a duplicate group.

**Body:**
```json
{
  "action": "keep_one",       // keep_one, keep_all, merge, ignore
  "keep_expense_id": 10       // Required for keep_one
}
```

**Actions:**
| Action | Description |
|--------|-------------|
| keep_one | Keep specified expense, delete others |
| keep_all | Mark as not duplicates (false positive) |
| merge | Keep oldest expense, delete others |
| ignore | Ignore this group |

### `GET /dedup/stats`

Get deduplication statistics.

**Response:**
```json
{
  "total_expenses": 156,
  "fingerprinted": 156,
  "coverage": 100.0,
  "groups": {
    "pending": 3,
    "resolved": 5,
    "ignored": 1,
    "total": 9
  }
}
```

## Database Changes

- Added `fingerprint` column to `expenses` (VARCHAR(64), nullable)
- New `duplicate_groups` table with status tracking
- Indexes on fingerprint and user/status
- Migration: `app/db/028_transaction_dedup.sql`

## Technical Details

- Fingerprints are computed on-demand during scans
- Scans are idempotent — re-scanning updates fingerprints and finds new duplicates
- Resolution is permanent — deleted expenses are removed from the database
- Text normalization strips reference numbers (ref:, txn:, #) for better matching
