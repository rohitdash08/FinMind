import celery
import requests
import logging
from core.celery_app import app
from utils.idempotency import is_processed, mark_processed
from utils.dlq import save_to_dlq

logger = logging.getLogger(__name__)

class ResilientTask(celery.Task):
    """Base task class that handles permanent failures by routing them to a Dead Letter Queue (DLQ)."""
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        save_to_dlq(task_id=task_id, payload=(args, kwargs), exception=str(exc))
        super().on_failure(exc, task_id, args, kwargs, einfo)

@app.task(
    base=ResilientTask,
    bind=True,
    autoretry_for=(requests.exceptions.RequestException,), 
    retry_kwargs={'max_retries': 5},
    retry_backoff=2,       # Starts at 2 seconds
    retry_backoff_max=120, # Caps at 2 minutes
    retry_jitter=True      # Adds random jitter to prevent thundering herd when services recover
)
def fetch_financial_data(self, api_endpoint: str, idempotency_key: str):
    """
    Fetches financial data from an external API.
    Retries automatically on network issues and checks idempotency before executing.
    """
    if is_processed(idempotency_key):
        logger.info(f"Task already processed for key: {idempotency_key}")
        return {"status": "Already processed", "idempotency_key": idempotency_key}
        
    logger.info(f"Fetching financial data from {api_endpoint}")
    response = requests.get(api_endpoint, timeout=10)
    response.raise_for_status()
    
    # Core logic (processing data...)
    data = response.json()
    
    # Mark as processed at the end of successful execution
    mark_processed(idempotency_key)
    return {"status": "Success", "data": data}