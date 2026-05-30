from datetime import datetime
from enum import Enum
from .extensions import db


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    DEAD = "DEAD"


class BackgroundJob(db.Model):
    __tablename__ = "background_jobs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    job_type = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default=JobStatus.PENDING.value, nullable=False)
    attempt = db.Column(db.Integer, default=0, nullable=False)
    max_retries = db.Column(db.Integer, default=3, nullable=False)
    retry_backoff_seconds = db.Column(db.Integer, default=60, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
