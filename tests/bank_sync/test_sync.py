"""Tests for sync engine and scheduler."""

import time
from datetime import datetime, timedelta
from typing import List, Optional

import pytest

from connectors.base import ConnectorError
from connectors.registry import ConnectorRegistry
from models.sync_state import SyncStatus
from models.transaction import Transaction
from sync.engine import SyncEngine
from sync.scheduler import SyncScheduler


class TestSyncEngine:
    def setup_method(self):
        self.registry = ConnectorRegistry()
        self.registry.auto_register()
        self.engine = SyncEngine(registry=self.registry)

    def test_add_connector(self):
        conn = self.engine.add_connector("mock", connector_id="e-mock")
        assert "e-mock" in self.engine.connector_ids
        assert conn.connector_type == "mock"

    def test_add_duplicate_raises(self):
        self.engine.add_connector("mock", connector_id="dup")
        with pytest.raises(ConnectorError, match="already exists"):
            self.engine.add_connector("mock", connector_id="dup")

    def test_remove_connector(self):
        self.engine.add_connector("mock", connector_id="rm-test")
        self.engine.remove_connector("rm-test")
        assert "rm-test" not in self.engine.connector_ids

    def test_remove_nonexistent_raises(self):
        with pytest.raises(ConnectorError, match="not found"):
            self.engine.remove_connector("ghost")

    def test_connect_all(self):
        self.engine.add_connector("mock", connector_id="c1")
        self.engine.add_connector("mock", connector_id="c2")
        results = self.engine.connect_all()
        assert results == {"c1": True, "c2": True}

    def test_disconnect_all(self):
        self.engine.add_connector("mock", connector_id="d1")
        self.engine.connect_all()
        self.engine.disconnect_all()
        # No error means success

    def test_sync_all_full_import(self):
        self.engine.add_connector("mock", connector_id="s1")
        self.engine.connect_all()
        end = datetime.utcnow()
        start = end - timedelta(days=5)
        results = self.engine.sync_all(start_date=start, end_date=end, full_import=True)
        assert "s1" in results
        assert len(results["s1"]) > 0

    def test_sync_all_skips_disconnected(self):
        self.engine.add_connector("mock", connector_id="skip1")
        # Don't connect
        results = self.engine.sync_all()
        assert results["skip1"] == []

    def test_sync_one(self):
        self.engine.add_connector("mock", connector_id="one1")
        self.engine.connect_all()
        end = datetime.utcnow()
        start = end - timedelta(days=3)
        txns = self.engine.sync_one("one1", start_date=start, end_date=end, full_import=True)
        assert len(txns) > 0

    def test_sync_one_nonexistent(self):
        with pytest.raises(ConnectorError, match="not found"):
            self.engine.sync_one("nope")

    def test_sync_state_tracking(self):
        self.engine.add_connector("mock", connector_id="st1")
        self.engine.connect_all()
        states = self.engine.sync_states
        assert states["st1"].status == SyncStatus.IDLE

        self.engine.sync_all(full_import=True)
        states = self.engine.sync_states
        assert states["st1"].status == SyncStatus.SUCCESS
        assert states["st1"].total_synced > 0

    def test_sync_callback(self):
        captured: List[tuple] = []

        def on_sync(cid, state, txns):
            captured.append((cid, len(txns)))

        self.engine.on_sync(on_sync)
        self.engine.add_connector("mock", connector_id="cb1")
        self.engine.connect_all()
        self.engine.sync_all(full_import=True)
        assert len(captured) == 1
        assert captured[0][0] == "cb1"
        assert captured[0][1] > 0

    def test_get_health(self):
        self.engine.add_connector("mock", connector_id="h1")
        self.engine.connect_all()
        self.engine.sync_all(full_import=True)
        health = self.engine.get_health()
        assert "h1" in health
        assert health["h1"]["connected"] is True
        assert health["h1"]["healthy"] is True
        assert health["h1"]["status"] == "success"
        assert health["h1"]["total_synced"] > 0

    def test_incremental_refresh(self):
        self.engine.add_connector("mock", connector_id="inc1")
        self.engine.connect_all()
        # First sync: full import
        self.engine.sync_all(full_import=True)
        count1 = self.engine.sync_states["inc1"].total_synced
        # Second sync: incremental refresh
        self.engine.sync_all(full_import=False)
        count2 = self.engine.sync_states["inc1"].total_synced
        assert count2 >= count1

    def test_remove_disconnects(self):
        self.engine.add_connector("mock", connector_id="rd1")
        self.engine.connect_all()
        self.engine.remove_connector("rd1")
        assert "rd1" not in self.engine.connector_ids


class TestSyncScheduler:
    def setup_method(self):
        self.registry = ConnectorRegistry()
        self.registry.auto_register()
        self.engine = SyncEngine(registry=self.registry)
        self.engine.add_connector("mock", connector_id="sched1")
        self.engine.connect_all()

    def test_run_once(self):
        scheduler = SyncScheduler(self.engine, default_interval=60)
        results = scheduler.run_once()
        assert "sched1" in results
        assert results["sched1"] > 0

    def test_interval_enforcement(self):
        scheduler = SyncScheduler(self.engine, default_interval=60)
        # First run should sync
        r1 = scheduler.run_once()
        assert "sched1" in r1
        # Immediate second run should skip (interval not elapsed)
        r2 = scheduler.run_once()
        assert "sched1" not in r2

    def test_set_interval(self):
        scheduler = SyncScheduler(self.engine, default_interval=3600)
        scheduler.set_interval("sched1", 120)
        assert scheduler.get_interval("sched1") == 120

    def test_set_interval_too_low(self):
        scheduler = SyncScheduler(self.engine, default_interval=3600)
        with pytest.raises(ValueError, match="at least 60"):
            scheduler.set_interval("sched1", 30)

    def test_start_stop(self):
        scheduler = SyncScheduler(self.engine, default_interval=3600)
        scheduler.start()
        assert scheduler.is_running is True
        scheduler.stop(timeout=2)
        assert scheduler.is_running is False

    def test_double_start(self):
        scheduler = SyncScheduler(self.engine, default_interval=3600)
        scheduler.start()
        scheduler.start()  # Should warn but not crash
        scheduler.stop(timeout=2)

    def test_status(self):
        scheduler = SyncScheduler(self.engine, default_interval=3600)
        status = scheduler.status()
        assert status["running"] is False
        assert "sched1" in status["connectors"]
        assert status["connectors"]["sched1"]["interval"] == 3600

    def test_callback(self):
        captured: List[tuple] = []

        def on_cycle(cid, count, error):
            captured.append((cid, count, error))

        scheduler = SyncScheduler(self.engine, default_interval=60, on_cycle=on_cycle)
        scheduler.run_once()
        assert len(captured) == 1
        assert captured[0][0] == "sched1"
        assert captured[0][1] > 0
        assert captured[0][2] is None
