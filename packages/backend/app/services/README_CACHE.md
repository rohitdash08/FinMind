# Cache Service Documentation

## Overview

The cache service provides Redis-backed caching with intelligent TTL strategies
and automatic invalidation for the FinMind backend.

## Architecture

### Core Components

- **`cache_get(key)`** / **`cache_set(key, value, ttl)`** — Low-level cache
  operations. Fully backward-compatible with existing callers.
- **`cache_delete_patterns(patterns)`** — Scan-and-delete by glob pattern.
- **`CacheManager`** — High-level singleton (`cache_manager`) that adds
  get-or-set semantics, typed invalidation, and stats.

### Singleton

```python
from app.services.cache import cache_manager
```

All routes should import and use `cache_manager` rather than calling
`cache_get` / `cache_set` directly for new code.

## TTL Strategies

Data is cached with a TTL chosen by its volatility:

| Strategy   | TTL       | Use case                                  |
|------------|-----------|-------------------------------------------|
| `realtime` | 30 s      | Highly volatile — pending reminders       |
| `short`    | 5 min     | Frequently changing — expenses, bills     |
| `medium`   | 30 min    | Moderately stable — dashboard, categories |
| `long`     | 1 hr      | Stable — insights, monthly summaries      |
| `static`   | 24 hr     | Rarely changing — user profile            |

Default (if unspecified) is `medium` (30 min).

## Usage

### Read-through caching (get_or_set)

```python
from app.services.cache import cache_manager, dashboard_summary_key

key = dashboard_summary_key(uid, ym)
result = cache_manager.get_or_set(key, compute_payload, ttl_strategy="medium")
```

`get_or_set` checks the cache first. On a miss it calls `compute_payload()`,
stores the result, and returns it. Redis errors are caught and logged; the
factory result is still returned to the caller.

### Invalidation

```python
# Clear all caches for a user (after account-level changes)
cache_manager.invalidate_user(uid)

# Clear a specific cache type for a user (after expense create/update/delete)
cache_manager.invalidate_user_type(uid, "dashboard_summary")
cache_manager.invalidate_user_type(uid, "monthly_summary")
```

### Monitoring

```python
stats = cache_manager.get_stats()
# {
#   "hits": 1234,
#   "misses": 56,
#   "hit_rate": 0.9565,
#   "memory_used": "1.2M",
#   "keys": 42,
# }
```

An authenticated endpoint is also available:

```
GET /dashboard/cache-stats
Authorization: Bearer <token>
```

## Adding caching to a new route

1. Create a key function (or reuse an existing one):

   ```python
   def my_feature_key(user_id: int) -> str:
       return f"user:{user_id}:my_feature"
   ```

2. Use `get_or_set` in your route:

   ```python
   @bp.get("/my-feature")
   @jwt_required()
   def my_feature():
       uid = int(get_jwt_identity())
       key = my_feature_key(uid)
       result = cache_manager.get_or_set(key, lambda: compute(uid), ttl_strategy="short")
       return jsonify(result)
   ```

3. Invalidate on writes:

   ```python
   @bp.post("/my-feature")
   @jwt_required()
   def create_my_feature():
       # ... create ...
       cache_manager.invalidate_user_type(uid, "my_feature")
   ```

## Invalidation patterns

| Trigger                     | Invalidation call                                    |
|-----------------------------|------------------------------------------------------|
| Expense create/update/delete| `invalidate_user_type(uid, "dashboard_summary")`    |
|                             | `invalidate_user_type(uid, "monthly_summary")`       |
| Bill create/update/delete   | `invalidate_user_type(uid, "dashboard_summary")`    |
|                             | `invalidate_user_type(uid, "upcoming_bills")`        |
| Account settings change     | `invalidate_user(uid)`                               |

## Error handling

All Redis operations inside `CacheManager` are wrapped in try/except.
Failures are logged at WARNING level. On cache miss or Redis error,
the factory function is called and its result is returned directly —
the endpoint never fails because of a cache problem.
