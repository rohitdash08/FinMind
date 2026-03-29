import logging
import json
import os

logger = logging.getLogger(__name__)

# A simple file-based DLQ for demonstration; in production, route this to a DB table or alert service
DLQ_FILE = os.getenv("DLQ_FILE_PATH", "dlq.log")

def save_to_dlq(task_id: str, payload: tuple, exception: str):
    """Save a failed task to the Dead Letter Queue after max retries are exceeded."""
    dlq_entry = {
        "task_id": task_id,
        "payload": payload,
        "exception": exception,
    }
    logger.error(f"Task {task_id} failed permanently. Routing to DLQ. Payload: {payload}, Exception: {exception}")
    try:
        with open(DLQ_FILE, "a") as f:
            f.write(json.dumps(dlq_entry) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to DLQ: {e}")