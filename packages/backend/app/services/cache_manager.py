
from functools import wraps
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
import hashlib, json

class CacheManager:
    def __init__(self, redis_client=None, default_ttl=300):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self._local = {}

    def _key(self, prefix, user_id, params=None):
        parts = [prefix, str(user_id)]
        if params: parts.append(hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8])
        return ":".join(parts)

    def get(self, key):
        if self.redis:
            try:
                d = self.redis.get(key)
                if d: return json.loads(d)
            except: pass
        e = self._local.get(key)
        if e and e["exp"] > datetime.utcnow(): return e["val"]
        return None

    def set(self, key, value, ttl=None, tags=None):
        ttl = ttl or self.default_ttl
        if self.redis:
            try:
                self.redis.setex(key, ttl, json.dumps(value, default=str))
                for t in (tags or []): self.redis.sadd(f"tag:{t}", key); self.redis.expire(f"tag:{t}", ttl)
            except: pass
        self._local[key] = {"val": value, "exp": datetime.utcnow() + timedelta(seconds=ttl), "tags": tags or []}

    def invalidate_by_tag(self, tag):
        if self.redis:
            try:
                keys = self.redis.smembers(f"tag:{tag}")
                if keys: self.redis.delete(*keys)
                self.redis.delete(f"tag:{tag}")
            except: pass
        self._local = {k: v for k, v in self._local.items() if tag not in v.get("tags", [])}

    def invalidate_user(self, user_id): self.invalidate_by_tag(f"user:{user_id}")

    def cached(self, prefix, ttl=None, tags=None):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                uid = kwargs.get("user_id") or (args[0] if args else 0)
                key = self._key(prefix, uid, {k: v for k, v in kwargs.items() if k != "user_id"})
                result = self.get(key)
                if result is not None: return result
                result = func(*args, **kwargs)
                self.set(key, result, ttl=ttl, tags=[t.format(user_id=uid) for t in (tags or [])])
                return result
            return wrapper
        return decorator

cache = CacheManager()
