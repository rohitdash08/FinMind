// PATCH: 此為 AI 生成的修復建議，請人工審查後合併
# Transaction Deduplication

## Overview
FinMind now supports intelligent transaction deduplication during imports and syncs. The system uses fuzzy string matching based on configurable fields (e.g., date, amount, description) to detect potentially duplicate transactions, reducing manual cleanup.

## Configuration
Deduplication settings can be controlled via environment variables:

- `DEDUPLICATION_THRESHOLD` (default: 0.9) – similarity score (0–1) above which a transaction is considered a duplicate.
- `DEDUPLICATION_FIELDS` (default: `date,amount,description,category`) – comma-separated list of fields used to build the comparison fingerprint.

The logic is implemented in `src/utils/deduplication.ts` and is used by the transaction import and sync services.

## How It Works
1. Builds a normalized string fingerprint for each transaction from the configured fields.
2. Computes the similarity between the incoming transaction fingerprint and existing ones using a string comparison algorithm (e.g., Dice coefficient).
3. If the highest similarity meets or exceeds the threshold, the transaction is flagged as duplicate.

## Extending
You can override the default threshold per call by passing a `threshold` option to the `deduplicateTransactions` function.
