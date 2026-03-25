"""
Background Job Service with Retry and Monitoring

This module provides a robust background job execution system with:
- Exponential backoff retry mechanism
- Configurable retry limits
- Job status tracking and monitoring
- Prometheus metrics integration
- Dead letter queue for failed jobs
"""

import logging
import time
import threading
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Callable, Any, Optional, List
from dataclasses import dataclass
import random

from ..extensions import db
from ..observability import track_reminder_event

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Background job status enum."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    DEAD_LETTER = "DEAD_LETTER"


class JobType(str, Enum):
    """Background job types."""
    SEND_REMINDER = "SEND_REMINDER"
    SEND_EMAIL = "SEND_EMAIL"
    SEND_WHATSAPP = "SEND_WHATSAPP"
    PROCESS_RECURRING = "PROCESS_RECURRING"
    IMPORT_EXPENSES = "IMPORT_EXPENSES"
    GENERATE_INSIGHTS = "GENERATE_INSIGHTS"
    CLEANUP_OLD_DATA = "CLEANUP_OLD_DATA"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0  # 5 minutes max
    backoff_multiplier: float = 2.0
    jitter: bool = True  # Add random jitter to prevent thundering herd


DEFAULT_RETRY_CONFIG = RetryConfig()


class BackgroundJob(db.Model):
    """Model for tracking background jobs."""
    __tablename__ = "background_jobs"

    id = db.Column(db.Integer, primary_key=True)
    job_type = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(20), default=JobStatus.PENDING.value, nullable=False)
    priority = db.Column(db.Integer, default=0, nullable=False)  # Higher = more urgent
    
    # Retry tracking
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    max_retries = db.Column(db.Integer, default=3, nullable=False)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    
    # Timing
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Result
    result = db.Column(db.JSON, nullable=True)
    
    # User association (optional)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<BackgroundJob {self.id}: {self.job_type} - {self.status}>"


class JobMetrics:
    """Prometheus-style metrics for background jobs."""
    
    def __init__(self):
        self._jobs_created = 0
        self._jobs_succeeded = 0
        self._jobs_failed = 0
        self._jobs_retried = 0
        self._jobs_dead_letter = 0
        self._total_processing_time_ms = 0
        self._lock = threading.Lock()
    
    def record_job_created(self):
        with self._lock:
            self._jobs_created += 1
    
    def record_job_success(self, duration_ms: float):
        with self._lock:
            self._jobs_succeeded += 1
            self._total_processing_time_ms += duration_ms
    
    def record_job_failure(self):
        with self._lock:
            self._jobs_failed += 1
    
    def record_job_retry(self):
        with self._lock:
            self._jobs_retried += 1
    
    def record_dead_letter(self):
        with self._lock:
            self._jobs_dead_letter += 1
    
    def get_stats(self) -> dict:
        with self._lock:
            return {
                "jobs_created": self._jobs_created,
                "jobs_succeeded": self._jobs_succeeded,
                "jobs_failed": self._jobs_failed,
                "jobs_retried": self._jobs_retried,
                "jobs_dead_letter": self._jobs_dead_letter,
                "total_processing_time_ms": self._total_processing_time_ms,
                "avg_processing_time_ms": (
                    self._total_processing_time_ms / self._jobs_succeeded 
                    if self._jobs_succeeded > 0 else 0
                ),
            }


# Global metrics instance
job_metrics = JobMetrics()


class BackgroundJobService:
    """
    Service for managing and executing background jobs with retry logic.
    
    Features:
    - Exponential backoff with jitter
    - Configurable retry limits per job
    - Dead letter queue for permanently failed jobs
    - Job prioritization
    - Comprehensive logging and metrics
    """
    
    # Registry of job handlers
    _handlers: dict[str, Callable] = {}
    
    @classmethod
    def register_handler(cls, job_type: JobType, handler: Callable):
        """Register a handler function for a job type."""
        cls._handlers[job_type.value] = handler
        logger.info(f"Registered handler for job type: {job_type.value}")
    
    @classmethod
    def enqueue(
        cls,
        job_type: JobType,
        payload: Optional[dict] = None,
        priority: int = 0,
        max_retries: int = 3,
        user_id: Optional[int] = None,
    ) -> BackgroundJob:
        """
        Create and enqueue a new background job.
        
        Args:
            job_type: Type of job to execute
            payload: Job-specific data
            priority: Job priority (higher = more urgent)
            max_retries: Maximum retry attempts
            user_id: Optional user association
            
        Returns:
            Created BackgroundJob instance
        """
        job = BackgroundJob(
            job_type=job_type.value,
            payload=payload or {},
            priority=priority,
            max_retries=max_retries,
            user_id=user_id,
            status=JobStatus.PENDING.value,
        )
        db.session.add(job)
        db.session.commit()
        
        job_metrics.record_job_created()
        logger.info(f"Enqueued job {job.id}: {job_type.value}")
        
        return job
    
    @classmethod
    def calculate_backoff_delay(
        cls, 
        retry_count: int, 
        config: RetryConfig = DEFAULT_RETRY_CONFIG
    ) -> float:
        """
        Calculate the delay before the next retry using exponential backoff.
        
        Formula: min(max_delay, initial_delay * (multiplier ^ retry_count))
        With optional jitter to prevent thundering herd.
        """
        delay = min(
            config.max_delay_seconds,
            config.initial_delay_seconds * (config.backoff_multiplier ** retry_count)
        )
        
        if config.jitter:
            # Add random jitter: ±25% of the delay
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0, delay)  # Ensure non-negative
        
        return delay
    
    @classmethod
    def execute_job(cls, job: BackgroundJob) -> bool:
        """
        Execute a single background job with retry logic.
        
        Args:
            job: BackgroundJob to execute
            
        Returns:
            True if job succeeded, False otherwise
        """
        handler = cls._handlers.get(job.job_type)
        
        if not handler:
            logger.error(f"No handler registered for job type: {job.job_type}")
            job.status = JobStatus.DEAD_LETTER.value
            job.last_error = f"No handler for job type: {job.job_type}"
            job.completed_at = datetime.utcnow()
            db.session.commit()
            job_metrics.record_dead_letter()
            return False
        
        # Update job status
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.utcnow()
        db.session.commit()
        
        start_time = time.perf_counter()
        
        try:
            # Execute the handler
            result = handler(job.payload)
            
            # Mark as succeeded
            duration_ms = (time.perf_counter() - start_time) * 1000
            job.status = JobStatus.SUCCEEDED.value
            job.completed_at = datetime.utcnow()
            job.result = {"success": True, "data": result}
            db.session.commit()
            
            job_metrics.record_job_success(duration_ms)
            logger.info(f"Job {job.id} succeeded in {duration_ms:.2f}ms")
            
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job.id} failed: {error_msg}")
            
            # Check if we can retry
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = JobStatus.RETRYING.value
                job.last_error = error_msg
                
                # Calculate next retry time
                delay = cls.calculate_backoff_delay(job.retry_count)
                job.next_retry_at = datetime.utcnow().fromtimestamp(
                    datetime.utcnow().timestamp() + delay
                )
                
                db.session.commit()
                job_metrics.record_job_retry()
                logger.info(f"Job {job.id} scheduled for retry {job.retry_count}/{job.max_retries} in {delay:.2f}s")
                
                return False
            else:
                # Max retries exceeded - move to dead letter
                job.status = JobStatus.DEAD_LETTER.value
                job.last_error = error_msg
                job.completed_at = datetime.utcnow()
                db.session.commit()
                
                job_metrics.record_dead_letter()
                logger.error(f"Job {job.id} moved to dead letter queue after {job.retry_count} retries")
                
                return False
    
    @classmethod
    def process_pending_jobs(cls, limit: int = 10) -> dict:
        """
        Process pending and retry-ready jobs.
        
        Args:
            limit: Maximum number of jobs to process in one batch
            
        Returns:
            Processing statistics
        """
        now = datetime.utcnow()
        
        # Query pending jobs and jobs ready for retry
        jobs = BackgroundJob.query.filter(
            db.or_(
                BackgroundJob.status == JobStatus.PENDING.value,
                db.and_(
                    BackgroundJob.status == JobStatus.RETRYING.value,
                    BackgroundJob.next_retry_at <= now
                )
            )
        ).order_by(
            BackgroundJob.priority.desc(),
            BackgroundJob.created_at.asc()
        ).limit(limit).all()
        
        stats = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "retried": 0,
        }
        
        for job in jobs:
            result = cls.execute_job(job)
            stats["processed"] += 1
            
            if result:
                stats["succeeded"] += 1
            else:
                if job.status == JobStatus.RETRYING.value:
                    stats["retried"] += 1
                else:
                    stats["failed"] += 1
        
        return stats
    
    @classmethod
    def get_job_status(cls, job_id: int) -> Optional[dict]:
        """Get the status of a specific job."""
        job = BackgroundJob.query.get(job_id)
        if not job:
            return None
        
        return {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "last_error": job.last_error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "result": job.result,
        }
    
    @classmethod
    def get_dead_letter_jobs(cls, limit: int = 50) -> List[dict]:
        """Get jobs in the dead letter queue."""
        jobs = BackgroundJob.query.filter(
            BackgroundJob.status == JobStatus.DEAD_LETTER.value
        ).order_by(BackgroundJob.completed_at.desc()).limit(limit).all()
        
        return [cls.get_job_status(job.id) for job in jobs]
    
    @classmethod
    def retry_dead_letter_job(cls, job_id: int) -> bool:
        """
        Manually retry a job from the dead letter queue.
        
        Args:
            job_id: ID of the job to retry
            
        Returns:
            True if job was queued for retry, False if not found
        """
        job = BackgroundJob.query.get(job_id)
        if not job or job.status != JobStatus.DEAD_LETTER.value:
            return False
        
        # Reset job for retry
        job.status = JobStatus.PENDING.value
        job.retry_count = 0
        job.next_retry_at = None
        job.completed_at = None
        db.session.commit()
        
        logger.info(f"Job {job_id} manually queued for retry")
        return True
    
    @classmethod
    def cleanup_old_jobs(cls, days: int = 30) -> int:
        """
        Remove completed jobs older than specified days.
        
        Args:
            days: Number of days to keep completed jobs
            
        Returns:
            Number of jobs deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        deleted = BackgroundJob.query.filter(
            BackgroundJob.status.in_([
                JobStatus.SUCCEEDED.value,
                JobStatus.DEAD_LETTER.value
            ]),
            BackgroundJob.completed_at < cutoff
        ).delete()
        
        db.session.commit()
        logger.info(f"Cleaned up {deleted} old jobs")
        
        return deleted


# Convenience function for creating retry configurations
def create_retry_config(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 300.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True
) -> RetryConfig:
    """Create a custom retry configuration."""
    return RetryConfig(
        max_retries=max_retries,
        initial_delay_seconds=initial_delay,
        max_delay_seconds=max_delay,
        backoff_multiplier=backoff_multiplier,
        jitter=jitter
    )