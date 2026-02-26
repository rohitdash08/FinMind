"""Simple scheduler for periodic connector refresh."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional

from sync.engine import SyncEngine

logger = logging.getLogger(__name__)

SchedulerCallback = Callable[[str, int, Optional[Exception]], None]


class SyncScheduler:
    """Lightweight scheduler for periodic bank sync operations.

    Runs sync cycles on a configurable interval using a background thread.
    Supports per-connector intervals and global defaults.

    Usage:
        engine = SyncEngine()
        # ... add connectors, connect ...

        scheduler = SyncScheduler(engine, default_interval=3600)
        scheduler.start()
        # ... later ...
        scheduler.stop()
    """

    def __init__(
        self,
        engine: SyncEngine,
        default_interval: int = 3600,
        on_cycle: Optional[SchedulerCallback] = None,
    ):
        """
        Args:
            engine: The SyncEngine to drive.
            default_interval: Default seconds between sync cycles.
            on_cycle: Optional callback(connector_id, txn_count, error) after each cycle.
        """
        self._engine = engine
        self._default_interval = default_interval
        self._on_cycle = on_cycle
        self._intervals: Dict[str, int] = {}
        self._last_run: Dict[str, float] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def set_interval(self, connector_id: str, seconds: int) -> None:
        """Set a custom sync interval for a specific connector.

        Args:
            connector_id: The connector to configure.
            seconds: Interval in seconds between syncs.
        """
        if seconds < 60:
            raise ValueError("Interval must be at least 60 seconds.")
        self._intervals[connector_id] = seconds

    def get_interval(self, connector_id: str) -> int:
        """Get the effective interval for a connector."""
        return self._intervals.get(connector_id, self._default_interval)

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self._running:
            logger.warning("Scheduler is already running.")
            return

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="sync-scheduler")
        self._thread.start()
        logger.info("Sync scheduler started (default interval: %ds).", self._default_interval)

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the scheduler and wait for the thread to finish.

        Args:
            timeout: Max seconds to wait for thread to stop.
        """
        if not self._running:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._running = False
        logger.info("Sync scheduler stopped.")

    def run_once(self) -> Dict[str, int]:
        """Run a single sync cycle for all due connectors.

        Returns:
            Dict of connector_id -> transaction count.
        """
        results: Dict[str, int] = {}
        now = time.time()

        for cid in self._engine.connector_ids:
            interval = self.get_interval(cid)
            last = self._last_run.get(cid, 0)

            if (now - last) < interval:
                continue

            try:
                txns = self._engine.sync_one(cid)
                count = len(txns)
                results[cid] = count
                self._last_run[cid] = now
                logger.info("Scheduled sync for %s: %d transactions.", cid, count)
                if self._on_cycle:
                    self._on_cycle(cid, count, None)
            except Exception as e:
                results[cid] = 0
                self._last_run[cid] = now  # avoid tight retry loop
                logger.error("Scheduled sync failed for %s: %s", cid, e)
                if self._on_cycle:
                    self._on_cycle(cid, 0, e)

        return results

    def _run_loop(self) -> None:
        """Main scheduler loop running in background thread."""
        logger.debug("Scheduler loop started.")
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)

            # Sleep in small increments so we can respond to stop quickly
            for _ in range(min(self._default_interval, 60)):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

        logger.debug("Scheduler loop exited.")

    def status(self) -> dict:
        """Get scheduler status summary."""
        return {
            "running": self._running,
            "default_interval": self._default_interval,
            "connectors": {
                cid: {
                    "interval": self.get_interval(cid),
                    "last_run": datetime.utcfromtimestamp(self._last_run[cid]).isoformat()
                    if cid in self._last_run else None,
                    "next_due_in": max(
                        0,
                        int(self.get_interval(cid) - (time.time() - self._last_run.get(cid, 0)))
                    ),
                }
                for cid in self._engine.connector_ids
            },
        }
