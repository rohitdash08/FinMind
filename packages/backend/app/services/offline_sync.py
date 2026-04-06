"""Offline-first sync with conflict resolution (issue #98)."""
import json, logging, time, uuid
from ..extensions import db, redis_client

logger = logging.getLogger("finmind.sync")
QUEUE_KEY = "sync:queue:{user_id}"
CONFLICT_KEY = "sync:conflicts:{user_id}"

def queue_operation(user_id: int, op: dict) -> str:
    """Queue an offline operation for sync."""
    op_id = str(uuid.uuid4())
    op.update({"id": op_id, "user_id": user_id, "queued_at": time.time(), "status": "pending"})
    redis_client.rpush(QUEUE_KEY.format(user_id=user_id), json.dumps(op))
    return op_id

def get_pending_ops(user_id: int) -> list:
    raw = redis_client.lrange(QUEUE_KEY.format(user_id=user_id), 0, -1)
    return [json.loads(r) for r in raw]

def resolve_conflict(local: dict, server: dict, strategy: str = "last_write_wins") -> dict:
    """Resolve sync conflict between local and server versions."""
    if strategy == "last_write_wins":
        return local if local.get("updated_at", 0) >= server.get("updated_at", 0) else server
    elif strategy == "server_wins":
        return server
    elif strategy == "client_wins":
        return local
    elif strategy == "merge":
        merged = {**server, **{k: v for k, v in local.items() if v is not None}}
        return merged
    return server

def get_sync_status(user_id: int) -> dict:
    pending = redis_client.llen(QUEUE_KEY.format(user_id=user_id))
    conflicts = redis_client.llen(CONFLICT_KEY.format(user_id=user_id))
    return {"pending_ops": pending, "conflicts": conflicts,
            "in_sync": pending == 0 and conflicts == 0}
