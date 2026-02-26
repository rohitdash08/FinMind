"""Sync state tracking for bank connectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SyncStatus(str, Enum):
    """Status of a sync operation."""
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class SyncState:
    """Tracks the state of a connector's sync operations."""
    connector_id: str
    status: SyncStatus = SyncStatus.IDLE
    last_sync_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    cursor: Optional[str] = None
    error_message: Optional[str] = None
    error_count: int = 0
    total_synced: int = 0
    metadata: dict = field(default_factory=dict)

    def mark_started(self) -> None:
        """Mark sync as in progress."""
        self.status = SyncStatus.SYNCING
        self.error_message = None

    def mark_success(self, synced_count: int = 0, cursor: Optional[str] = None) -> None:
        """Mark sync as successful."""
        now = datetime.utcnow()
        self.status = SyncStatus.SUCCESS
        self.last_sync_at = now
        self.last_success_at = now
        self.total_synced += synced_count
        self.error_count = 0
        self.error_message = None
        if cursor is not None:
            self.cursor = cursor

    def mark_failed(self, error: str) -> None:
        """Mark sync as failed."""
        self.status = SyncStatus.FAILED
        self.last_sync_at = datetime.utcnow()
        self.error_message = error
        self.error_count += 1

    def mark_partial(self, synced_count: int = 0, error: str = "") -> None:
        """Mark sync as partially complete."""
        self.status = SyncStatus.PARTIAL
        self.last_sync_at = datetime.utcnow()
        self.total_synced += synced_count
        if error:
            self.error_message = error

    @property
    def is_healthy(self) -> bool:
        """Check if the connector is in a healthy state."""
        return self.error_count < 3 and self.status != SyncStatus.FAILED

    @property
    def needs_sync(self) -> bool:
        """Check if a sync is needed (never synced or idle)."""
        return self.last_success_at is None or self.status == SyncStatus.IDLE
