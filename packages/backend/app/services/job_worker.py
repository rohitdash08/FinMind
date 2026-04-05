"""Background job queue architecture (issue #71)."""
import json, logging, signal, time, uuid
from typing import Callable
from ..extensions import redis_client

logger = logging.getLogger("finmind.worker")

QUEUE = "jobs:work_queue"
PROCESSING = "jobs:processing"
DEAD = "jobs:dead_letter"
STATUS = "jobs:status:"
WORKER_TTL = 30  # seconds before job considered abandoned


def submit(job_type: str, payload: dict, priority: int = 5) -> str:
    """Submit a job. priority 1=highest, 10=lowest."""
    jid = str(uuid.uuid4())
    job = {"id": jid, "type": job_type, "payload": payload,
           "priority": priority, "submitted_at": time.time(), "attempts": 0}
    score = priority * 1e12 + time.time()
    redis_client.zadd(QUEUE, {json.dumps(job): score})
    _set_status(jid, "queued")
    logger.info("Job submitted: %s type=%s priority=%d", jid, job_type, priority)
    return jid


def claim_job() -> dict | None:
    """Atomically claim the highest-priority pending job."""
    raw = redis_client.zpopmin(QUEUE, 1)
    if not raw: return None
    job_str, _ = raw[0]
    job = json.loads(job_str)
    job["claimed_at"] = time.time()
    redis_client.setex(f"{PROCESSING}:{job['id']}", WORKER_TTL, json.dumps(job))
    _set_status(job["id"], "processing")
    return job


def complete_job(job_id: str, result: dict = None):
    redis_client.delete(f"{PROCESSING}:{job_id}")
    _set_status(job_id, "completed", result=result)
    logger.info("Job completed: %s", job_id)


def fail_job(job_id: str, error: str, max_retries: int = 3):
    raw = redis_client.get(f"{PROCESSING}:{job_id}")
    if not raw: return
    job = json.loads(raw)
    job["attempts"] = job.get("attempts", 0) + 1
    redis_client.delete(f"{PROCESSING}:{job_id}")

    if job["attempts"] < max_retries:
        delay = 2 ** job["attempts"]
        score = job["priority"] * 1e12 + time.time() + delay
        redis_client.zadd(QUEUE, {json.dumps(job): score})
        _set_status(job_id, f"retry_{job['attempts']}", error=error)
        logger.warning("Job %s retry %d in %ds", job_id, job["attempts"], delay)
    else:
        redis_client.rpush(DEAD, json.dumps({**job, "final_error": error}))
        _set_status(job_id, "dead", error=error)
        logger.error("Job %s dead after %d attempts", job_id, job["attempts"])


def get_status(job_id: str) -> dict | None:
    raw = redis_client.get(f"{STATUS}{job_id}")
    return json.loads(raw) if raw else None


def queue_depth() -> int:
    return redis_client.zcard(QUEUE)


def _set_status(job_id, status, result=None, error=None):
    data = {"job_id": job_id, "status": status, "ts": time.time()}
    if result: data["result"] = result
    if error: data["error"] = error
    redis_client.setex(f"{STATUS}{job_id}", 86400 * 7, json.dumps(data))
