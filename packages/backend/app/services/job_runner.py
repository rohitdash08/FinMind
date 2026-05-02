import logging
import time
import traceback
from datetime import datetime, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import BackgroundJob, JobStatus
from ..observability import track_background_job

logger = logging.getLogger("finmind.jobs")

# Type alias for job handler functions
JobHandler = callable  # (payload: dict | None) -> None


class BackgroundJobRunner:
    """Resilient background job runner with exponential backoff and dead-letter support."""

    def __init__(self):
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler function for a given job type."""
        self._handlers[job_type] = handler
        logger.info("Registered job handler for type=%s", job_type)

    def enqueue_job(
        self,
        job_type: str,
        payload: dict | None = None,
        max_retries: int = 5,
    ) -> BackgroundJob:
        """Create a new background job record in pending state."""
        job = BackgroundJob(
            job_type=job_type,
            payload=payload,
            status=JobStatus.PENDING.value,
            max_retries=max_retries,
        )
        db.session.add(job)
        db.session.commit()
        logger.info("Enqueued job id=%s type=%s", job.id, job_type)
        return job

    def execute_job(self, job_id: int) -> BackgroundJob:
        """Execute a single job by id with error handling and retry logic."""
        job = db.session.get(BackgroundJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status not in (
            JobStatus.PENDING.value,
            JobStatus.FAILED.value,
        ):
            logger.warning(
                "Job id=%s status=%s is not executable, skipping", job.id, job.status
            )
            return job

        handler = self._handlers.get(job.job_type)
        if not handler:
            job.status = JobStatus.DEAD_LETTER.value
            job.last_error = f"No handler registered for job type '{job.job_type}'"
            job.completed_at = datetime.utcnow()
            db.session.commit()
            logger.error(
                "Job id=%s type=%s dead-lettered: no handler", job.id, job.job_type
            )
            return job

        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.utcnow()
        job.attempts += 1
        job.next_retry_at = None
        db.session.commit()

        start_time = time.monotonic()
        try:
            handler(job.payload)
            elapsed = time.monotonic() - start_time
            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info(
                "Job id=%s type=%s completed in %.2fs", job.id, job.job_type, elapsed
            )
            track_background_job(job.job_type, "completed", elapsed)
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            job.last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            track_background_job(job.job_type, "failed", elapsed)

            if job.attempts >= job.max_retries:
                job.status = JobStatus.DEAD_LETTER.value
                job.completed_at = datetime.utcnow()
                logger.error(
                    "Job id=%s type=%s dead-lettered after %d attempts: %s",
                    job.id,
                    job.job_type,
                    job.attempts,
                    exc,
                )
            else:
                job.status = JobStatus.FAILED.value
                delay = self._backoff_delay(job.attempts)
                job.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                logger.warning(
                    "Job id=%s type=%s failed (attempt %d/%d), retry in %ds: %s",
                    job.id,
                    job.job_type,
                    job.attempts,
                    job.max_retries,
                    delay,
                    exc,
                )
            db.session.commit()

        return job

    def process_pending(self) -> list[BackgroundJob]:
        """Process all pending and retry-ready jobs. Returns list of processed jobs."""
        now = datetime.utcnow()
        jobs = (
            BackgroundJob.query.filter(
                (BackgroundJob.status == JobStatus.PENDING.value)
                | (
                    (BackgroundJob.status == JobStatus.FAILED.value)
                    & (BackgroundJob.next_retry_at <= now)
                )
            )
            .order_by(BackgroundJob.created_at)
            .all()
        )
        processed = []
        for job in jobs:
            try:
                result = self.execute_job(job.id)
                processed.append(result)
            except Exception:
                logger.exception("Unexpected error processing job id=%s", job.id)
        return processed

    def get_job_stats(self) -> dict:
        """Return counts by status and recent failure details."""
        rows = (
            db.session.query(BackgroundJob.status, func.count(BackgroundJob.id))
            .group_by(BackgroundJob.status)
            .all()
        )
        counts = {status: 0 for status in JobStatus.__members__.values()}
        for status, count in rows:
            counts[status] = count

        recent_failures = (
            BackgroundJob.query.filter(
                BackgroundJob.status.in_(
                    [JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value]
                )
            )
            .order_by(BackgroundJob.created_at.desc())
            .limit(10)
            .all()
        )

        return {
            "counts": counts,
            "recent_failures": [_job_to_dict(j) for j in recent_failures],
        }

    @staticmethod
    def _backoff_delay(attempt: int) -> int:
        """Calculate exponential backoff: min(2^attempt * 30, 3600) seconds."""
        return min(2 ** attempt * 30, 3600)


def _job_to_dict(job: BackgroundJob) -> dict:
    """Serialize a BackgroundJob to a dict for JSON responses."""
    return {
        "id": job.id,
        "job_type": job.job_type,
        "payload": job.payload,
        "status": job.status,
        "attempts": job.attempts,
        "max_retries": job.max_retries,
        "last_error": job.last_error,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


# Module-level singleton for convenience
job_runner = BackgroundJobRunner()
