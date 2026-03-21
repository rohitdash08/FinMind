"""
Celery configuration for FinMind background job processing.
Provides resilient task execution with retry, monitoring, and dead letter queue support.
"""

from celery import Celery
from kombu import Exchange, Queue
import os

# Celery app instance
celery_app = Celery("finmind")

# Configure from environment or defaults
celery_app.conf.update(
    # Broker and backend
    broker_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    result_backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Task execution
    task_track_started=True,
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit
    
    # Retry configuration
    task_default_retry_delay=60,  # 1 minute initial delay
    task_max_retries=5,
    
    # Rate limiting
    task_default_rate_limit="100/m",
    
    # Result backend
    result_expires=3600,  # 1 hour
    result_extended=True,
    
    # Worker configuration
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    
    # Queue definitions
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
        Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
        Queue("dead_letter", Exchange("dead_letter"), routing_key="dead_letter"),
    ),
    
    # Routing
    task_routes={
        "tasks.reminders.*": {"queue": "high_priority"},
        "tasks.ai.*": {"queue": "default"},
        "tasks.reports.*": {"queue": "low_priority"},
    },
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Auto-discover tasks from installed apps
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(bind=True, max_retries=5)
def example_task(self, x, y):
    """Example task demonstrating retry pattern."""
    try:
        result = x + y
        return {"result": result, "task_id": self.request.id}
    except Exception as exc:
        # Retry with exponential backoff
        countdown = 2 ** self.request.retries * 60  # 2, 4, 8, 16, 32 minutes
        raise self.retry(exc=exc, countdown=countdown)
