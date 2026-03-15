# Smart Caching Strategy for Dashboard & Analytics

## Overview

Intelligent multi-layer caching system for FinMind with smart invalidation, configurable TTL policies per data type, cache warming, and comprehensive monitoring.

## Architecture

```
Client Request → L1 Cache (Memory) → L2 Cache (Redis) → Database
                    ↑                      ↑
              ~1μs latency          ~1ms latency
```

### L1 Cache (In-Memory)
- Extremely fast local cache (Python dict)
- LRU-like eviction with configurable max size (default 1000 entries)
- Automatic expiry of stale entries
- Serves as hot cache for frequently accessed data

### L2 Cache (Redis)
- Persistent cache surviving process restarts
- Shared across multiple application instances
- TTL-based expiration
- Pattern-based key scanning for targeted invalidation

## Cache Policies

| Data Type | TTL | Prefix | Use Case |
|-----------|-----|--------|----------|
| dashboard | 5 min | `dash` | Dashboard widgets, overview data |
| analytics | 10 min | `analytics` | Spending trends, charts |
| insights | 15 min | `insights` | AI-generated insights |
| categories | 1 hour | `cat` | Category lists (rarely change) |
| user_prefs | 2 hours | `uprefs` | User preferences |
| summary | 30 min | `summary` | Financial summaries |
| report | 1 hour | `report` | Generated reports |
| default | 5 min | `misc` | Everything else |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cache/stats` | Cache statistics (L1 + L2) |
| POST | `/cache/stats/reset` | Reset statistics counters |
| GET | `/cache/policies` | List TTL policies |
| POST | `/cache/invalidate/user` | Invalidate current user's cache |
| POST | `/cache/invalidate/all` | Invalidate all caches |
| POST | `/cache/warm` | Pre-populate cache |
| POST | `/cache/test` | Test cache operations |
| GET | `/cache/health` | Cache health check |

## Usage

### Decorator-based Caching

```python
from app.services.smart_cache import cached

@cached(data_type="dashboard")
def get_dashboard_data(user_id):
    # Expensive computation...
    return {"total_spent": 5000, "budget_remaining": 2000}

# Second call returns cached result
data = get_dashboard_data(1)  # Cache miss → compute
data = get_dashboard_data(1)  # Cache hit → instant
```

### With Parameters

```python
@cached(data_type="analytics", key_params=["month", "category"])
def get_monthly_analytics(user_id, month=None, category=None):
    return compute_analytics(user_id, month, category)
```

### Manual Cache Operations

```python
from app.services.smart_cache import cache_get, cache_set, cache_delete

# Set
cache_set("custom:key", {"data": "value"}, ttl=600)

# Get
value = cache_get("custom:key")

# Delete
cache_delete("custom:key")
```

### Smart Invalidation

```python
from app.services.smart_cache import cache_invalidate_user

# When user adds an expense, invalidate related caches
cache_invalidate_user(user_id, ["dashboard", "analytics", "insights"])
```

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_smart_cache.py -v
```
