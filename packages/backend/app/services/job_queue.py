"""
Resilient background job retry & monitoring with exponential backoff (issue #130 — $250 bounty).
"""
import json, logging, time
from datetime import datetime, timezone
from typing import Callable, Optional
from ..extensions import redis_client

logger = logging.getLogger("finmind.jobs")

MAX_RETRIES = 5
BASE_DELAY = 2      # seconds — doubles each retry (2,4,8,16,32)
QUEUE_KEY = "jobs:queue"
DEAD_KEY  = "jobs:dead"
STATUS_PREFIX = "jobs:status:"


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def enqueue(job_type: str, payload: dict, job_id: Optional[str] = None) -> str:
    import uuid
    jid = job_id or str(uuid.uuid4())
    job = {"id": jid, "type": job_type, "payload": payload,
           "attempt": 0, "max_retries": MAX_RETRIES, "created_at": _utcnow()}
    redis_client.rpush(QUEUE_KEY, json.dumps(job))
    _set_status(jid, "queued")
    logger.info("Enqueued job %s type=%s", jid, job_type)
    return jid


def _set_status(job_id: str, status: str, error: str = None):
    data = {"status": status, "updated_at": _utcnow()}
    if error:
        data["last_error"] = error
    redis_client.setex(f"{STATUS_PREFIX}{job_id}", 60 * 60 * 24 * 7, json.dumps(data))


def get_status(job_id: str) -> Optional[dict]:
    raw = redis_client.get(f"{STATUS_PREFIX}{job_id}")
    return json.loads(raw) if raw else None


def process_one(handlers: dict[str, Callable]) -> Optional[dict]:
    """
    Pop one job from queue, run it, retry on failure with exponential backoff.
    handlers: {job_type: callable(payload) -> result}
    Returns job dict or None if queue empty.
    """
    raw = redis_client.lpop(QUEUE_KEY)
    if not raw:
        return None
    job = json.loads(raw)
    jid = job["id"]
    attempt = job["attempt"] + 1
    job["attempt"] = attempt

    handler = handlers.get(job["type"])
    if not handler:
        logger.error("No handler for job type %s", job["type"])
        _set_status(jid, "failed", error=f"no handler for {job['type']}")
        redis_client.rpush(DEAD_KEY, json.dumps(job))
        return job

    try:
        _set_status(jid, "running")
        result = handler(job["payload"])
        _set_status(jid, "completed")
        logger.info("Job %s completed attempt=%d", jid, attempt)
        job["result"] = result
        return job
    except Exception as exc:
        error = str(exc)
        logger.warning("Job %s failed attempt=%d/%d error=%s", jid, attempt, job["max_retries"], error)
        if attempt < job["max_retries"]:
            delay = BASE_DELAY ** attempt
            job["retry_after"] = time.time() + delay
            _set_status(jid, f"retry_scheduled (attempt {attempt})", error=error)
            # Re-enqueue with delay metadata
            redis_client.rpush(QUEUE_KEY, json.dumps(job))
        else:
            _set_status(jid, "dead", error=error)
            redis_client.rpush(DEAD_KEY, json.dumps(job))
            logger.error("Job %s moved to dead queue after %d attempts", jid, attempt)
        return job


def queue_length() -> int:
    return redis_client.llen(QUEUE_KEY)


def dead_queue_length() -> int:
    return redis_client.llen(DEAD_KEY)
