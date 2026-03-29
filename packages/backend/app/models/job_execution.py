"""Job execution tracking model for resilient retry & monitoring."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Enum as SAEnum, Text

from ..extensions import db


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    DEAD = "DEAD"  # exhausted all retries


class JobExecution(db.Model):
    """Tracks every background job execution with retry metadata."""

    __tablename__ = "job_executions"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(200), nullable=False, index=True)
    job_name = db.Column(db.String(200), nullable=False)
    status = db.Column(
        SAEnum(JobStatus, name="job_status", create_constraint=False),
        nullable=False,
        default=JobStatus.PENDING,
    )
    attempt = db.Column(db.Integer, nullable=False, default=1)
    max_retries = db.Column(db.Integer, nullable=False, default=3)
    error_message = db.Column(Text, nullable=True)
    error_traceback = db.Column(Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_name": self.job_name,
            "status": self.status.value if self.status else None,
            "attempt": self.attempt,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "next_retry_at": (
                self.next_retry_at.isoformat() if self.next_retry_at else None
            ),
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
