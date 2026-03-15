# Smart Payee & Merchant Alias Management

## Overview

Manage merchants/payees with alias support, fuzzy matching, merge functionality, and duplicate detection. Normalizes merchant names for consistent matching across transactions.

## API Endpoints

All endpoints require JWT authentication. Base path: `/merchants`

### Merchant CRUD

| Method | Path | Description |
|--------|------|-------------|
| GET | `/merchants` | List merchants (search, filter, sort, paginate) |
| POST | `/merchants` | Create merchant |
| GET | `/merchants/:id` | Get merchant details |
| PUT | `/merchants/:id` | Update merchant |
| DELETE | `/merchants/:id` | Delete merchant and aliases |

### Alias Management

| Method | Path | Description |
|--------|------|-------------|
| GET | `/merchants/:id/aliases` | List aliases |
| POST | `/merchants/:id/aliases` | Add alias |
| DELETE | `/merchants/:id/aliases/:alias_id` | Remove alias |

### Merge & Matching

| Method | Path | Description |
|--------|------|-------------|
| POST | `/merchants/merge` | Merge source merchants into target |
| GET | `/merchants/match?name=...` | Find merchant by name/alias |
| GET | `/merchants/duplicates` | Suggest duplicate merchants |

## Features

### Name Normalization
All merchant names and aliases are normalized: lowercased, special characters removed, whitespace collapsed. This ensures "Starbucks", "STARBUCKS", and "star bucks!" all match.

### Smart Matching
The `match` endpoint checks in order:
1. Exact match on merchant normalized name
2. Exact match on alias normalized name
3. Partial (substring) match on merchant name

### Merge
Merging source merchants into a target:
- Moves all aliases from sources to target
- Adds source merchant names as aliases of target
- Aggregates transaction counts and totals
- Preserves the latest transaction date
- Deletes source merchants

### Duplicate Detection
The `duplicates` endpoint finds potential duplicates using:
- Substring matching (one name contains the other)
- Word overlap (≥50% shared words)

## Database Schema

### merchants
- `id`, `user_id`, `name`, `normalized_name` (unique per user)
- `category_id`, `default_currency`, `notes`
- `transaction_count`, `total_spent`, `last_transaction_date`
- `created_at`, `updated_at`

### merchant_aliases
- `id`, `merchant_id`, `alias`, `normalized_alias` (unique per merchant)
- `created_at`

## Architecture

- **Migration:** `migrations/037_smart_payee.sql`
- **Models:** `Merchant`, `MerchantAlias` in `app/models.py`
- **Service:** `app/services/smart_payee.py`
- **Routes:** `app/routes/smart_payee.py`
- **Tests:** `tests/test_smart_payee.py` — 35 tests
