"""Smart payee & merchant alias management (issue #114)."""
import json, logging, re
from ..extensions import redis_client

logger = logging.getLogger("finmind.payee")
PREFIX = "payee:aliases:"
TTL = 60 * 60 * 24 * 365


def _key(user_id): return f"{PREFIX}{user_id}"


def set_alias(user_id: int, raw: str, alias: str, category_id: int = None):
    store = _load(user_id)
    store[raw.strip().lower()] = {"alias": alias.strip(), "category_id": category_id}
    _save(user_id, store)


def get_alias(user_id: int, raw: str) -> dict | None:
    store = _load(user_id)
    return store.get(raw.strip().lower())


def resolve(user_id: int, raw: str) -> str:
    """Return alias display name or cleaned raw name."""
    entry = get_alias(user_id, raw)
    if entry: return entry["alias"]
    # Auto-clean: strip transaction codes, uppercase, extra spaces
    cleaned = re.sub(r'\s+', ' ', re.sub(r'[*#\d]{4,}', '', raw)).strip().title()
    return cleaned or raw


def list_aliases(user_id: int) -> list:
    store = _load(user_id)
    return [{"raw": k, **v} for k, v in store.items()]


def delete_alias(user_id: int, raw: str) -> bool:
    store = _load(user_id)
    key = raw.strip().lower()
    if key not in store: return False
    del store[key]; _save(user_id, store); return True


def _load(user_id): 
    raw = redis_client.get(_key(user_id))
    return json.loads(raw) if raw else {}


def _save(user_id, store):
    redis_client.setex(_key(user_id), TTL, json.dumps(store))
