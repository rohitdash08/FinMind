import hashlib
import hmac
import json
import time
import requests
from datetime import datetime, timedelta
import uuid

from flask import current_app
from sqlalchemy import text

from app.extensions import db, scheduler, webhook_logger
from app.models import WebhookEndpoint, WebhookDeliveryAttempt

def generate_signature(secret: str, payload: str, timestamp: int) -> str:
    """Generates an HMAC-SHA256 signature for the webhook payload."""
    signed_payload = f"{timestamp}.{payload}"
    h = hmac.new(secret.encode('utf-8'), signed_payload.encode('utf-8'), hashlib.sha256)
    return h.hexdigest()

def _calculate_next_retry_time(attempt_number: int) -> datetime:
    """Calculates the next retry time using exponential backoff."""
    config = current_app.config
    initial_delay = config.get('WEBHOOK_INITIAL_RETRY_DELAY_SECONDS', 60)
    backoff_factor = config.get('WEBHOOK_RETRY_BACKOFF_FACTOR', 2)

    delay = initial_delay * (backoff_factor ** (attempt_number - 1))
    
    # Cap delay to prevent extremely long waits (e.g., max 24 hours)
    max_delay = config.get('WEBHOOK_MAX_RETRY_DELAY_SECONDS', 86400) # 24 hours
    delay = min(delay, max_delay)

    return datetime.utcnow() + timedelta(seconds=delay)

def dispatch_webhook_job(attempt_id: int):
    """
    Job function to dispatch a webhook delivery attempt.
    This function is intended to be called by APScheduler.
    """
    with current_app.app_context():
        attempt = WebhookDeliveryAttempt.query.get(attempt_id)
        if not attempt:
            webhook_logger.warning(f"Webhook delivery attempt {attempt_id} not found.")
            return

        if attempt.is_successful:
            webhook_logger.info(f"Attempt {attempt_id} already successful, skipping.")
            return

        endpoint = WebhookEndpoint.query.get(attempt.endpoint_id)
        if not endpoint or not endpoint.is_active:
            webhook_logger.warning(f"Endpoint {attempt.endpoint_id} for attempt {attempt_id} is inactive or not found. Marking attempt as failed.")
            attempt.is_successful = False
            attempt.completed_at = datetime.utcnow()
            attempt.error_message = "Endpoint inactive or not found"
            db.session.commit()
            return

        current_timestamp = int(time.time())
        signature = generate_signature(endpoint.secret, attempt.payload, current_timestamp)

        headers = {
            'Content-Type': 'application/json',
            'X-FinMind-Signature': f"t={current_timestamp},v1={signature}",
            'User-Agent': 'FinMind-Webhook-Agent/1.0',
            'X-FinMind-Event': attempt.event_type,
            'X-FinMind-Event-ID': attempt.event_id,
            'X-FinMind-Attempt': str(attempt.attempt_number)
        }

        webhook_logger.info(f"Dispatching webhook attempt {attempt.id} (Event: {attempt.event_type}, Attempt: {attempt.attempt_number}) to {endpoint.url}")

        try:
            response = requests.post(endpoint.url, data=attempt.payload, headers=headers, timeout=current_app.config.get('WEBHOOK_REQUEST_TIMEOUT_SECONDS', 10))
            attempt.status_code = response.status_code
            attempt.response_body = response.text[:1024] # Store a limited response body

            if 200 <= response.status_code < 300:
                attempt.is_successful = True
                attempt.completed_at = datetime.utcnow()
                webhook_logger.info(f"Webhook attempt {attempt.id} successful (Status: {response.status_code})")
            else:
                raise requests.exceptions.RequestException(f"HTTP Error: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            attempt.error_message = "Webhook request timed out"
            webhook_logger.warning(f"Webhook attempt {attempt.id} timed out.")
        except requests.exceptions.ConnectionError:
            attempt.error_message = "Failed to connect to webhook URL"
            webhook_logger.warning(f"Webhook attempt {attempt.id} connection error.")
        except requests.exceptions.RequestException as e:
            attempt.error_message = str(e)
            webhook_logger.error(f"Webhook attempt {attempt.id} failed: {e}")
        except Exception as e:
            attempt.error_message = f"An unexpected error occurred: {e}"
            webhook_logger.error(f"Webhook attempt {attempt.id} unexpected error: {e}")
        finally:
            if not attempt.is_successful:
                attempt.attempt_number += 1
                max_attempts = current_app.config.get('WEBHOOK_MAX_DELIVERY_ATTEMPTS', 5)
                if attempt.attempt_number <= max_attempts:
                    attempt.next_attempt_at = _calculate_next_retry_time(attempt.attempt_number)
                    webhook_logger.info(f"Scheduling retry for attempt {attempt.id} at {attempt.next_attempt_at}")
                else:
                    attempt.completed_at = datetime.utcnow()
                    webhook_logger.error(f"Webhook attempt {attempt.id} failed after {max_attempts} tries. No more retries.")
            db.session.commit()

def emit_event(user_id: int, event_type: str, data: dict):
    """
    Emits an event, finding relevant webhook endpoints and scheduling initial delivery.
    """
    with current_app.app_context():
        # Find active webhook endpoints for this user and event type
        # Using SQLAlchemy's text() for JSONB contains operator as a simple way
        # For more complex queries, consider using jsonb_ops in models.py or a custom type.
        
        # event_types column is JSONB, containing an array of strings.
        # We need to check if the `event_type` string is present in the `event_types` array.
        endpoints = WebhookEndpoint.query.filter(
            WebhookEndpoint.user_id == user_id,
            WebhookEndpoint.is_active == True,
            WebhookEndpoint.event_types.contains([event_type])
        ).all()

        if not endpoints:
            webhook_logger.info(f"No active webhook endpoints found for user {user_id} and event type '{event_type}'.")
            return

        event_uuid = str(uuid.uuid4())
        # Construct the full webhook payload
        payload_data = {
            "id": event_uuid,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
            "metadata": {
                "finmind_app_id": "finmind_backend"
            }
        }
        payload_str = json.dumps(payload_data, default=str) # default=str to handle datetime objects

        for endpoint in endpoints:
            try:
                # Create an initial delivery attempt record
                new_attempt = WebhookDeliveryAttempt(
                    endpoint_id=endpoint.id,
                    event_type=event_type,
                    event_id=event_uuid,
                    payload=payload_str,
                    attempt_number=1,
                    next_attempt_at=datetime.utcnow() # Schedule immediately
                )
                db.session.add(new_attempt)
                db.session.commit() # Commit to get attempt.id

                # Schedule the job via APScheduler
                scheduler.add_job(
                    id=f'webhook_dispatch_{new_attempt.id}_{uuid.uuid4()}', # Unique ID for each job
                    func=dispatch_webhook_job,
                    args=[new_attempt.id],
                    trigger='date',
                    run_date=new_attempt.next_attempt_at,
                    replace_existing=False # Don't replace if a job with this ID already exists (shouldn't happen with unique ID)
                )
                webhook_logger.info(f"Scheduled initial webhook dispatch for attempt {new_attempt.id} (Event: {event_type}) to endpoint {endpoint.url}.")

            except Exception as e:
                db.session.rollback()
                webhook_logger.error(f"Error scheduling webhook for endpoint {endpoint.id} (User: {user_id}, Event: {event_type}): {e}")


def webhook_scheduler_job():
    """
    Scheduler job to find and reschedule failed webhook attempts.
    This acts as a fallback/driver for APScheduler's missed jobs and ensures retries.
    """
    with current_app.app_context():
        # Query for non-successful attempts that are due for a retry
        # and haven't exceeded max attempts
        max_attempts = current_app.config.get('WEBHOOK_MAX_DELIVERY_ATTEMPTS', 5)
        due_attempts = WebhookDeliveryAttempt.query.filter(
            WebhookDeliveryAttempt.is_successful == False,
            WebhookDeliveryAttempt.next_attempt_at <= datetime.utcnow(),
            WebhookDeliveryAttempt.attempt_number <= max_attempts
        ).all()

        for attempt in due_attempts:
            # Check if a job for this attempt is already pending in APScheduler
            # This is a bit tricky with APScheduler's job management, as `get_job` by ID
            # only checks for exact job ID. Since we use a unique ID for each attempt scheduling,
            # we need to ensure we don't double-schedule.
            # For simplicity here, we rely on `dispatch_webhook_job` itself to handle re-queuing
            # and mark completion. This scheduler job primarily serves to trigger initial runs
            # or re-trigger if APScheduler somehow missed a scheduled job due to restart/etc.
            # A more robust solution might involve checking scheduler.get_jobs()
            # for a job associated with this attempt.id.
            
            # Re-schedule the job. APScheduler will handle if it's already running or completed.
            try:
                scheduler.add_job(
                    id=f'webhook_dispatch_{attempt.id}_{uuid.uuid4()}', # New unique ID for retry job
                    func=dispatch_webhook_job,
                    args=[attempt.id],
                    trigger='date',
                    run_date=datetime.utcnow(), # Run immediately
                    replace_existing=False
                )
                webhook_logger.info(f"Rescheduled failed webhook attempt {attempt.id} via scheduler job.")
            except Exception as e:
                webhook_logger.error(f"Failed to reschedule webhook attempt {attempt.id}: {e}")

