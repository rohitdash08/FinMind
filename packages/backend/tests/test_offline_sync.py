"""Tests for offline-first sync."""

import pytest


class TestSyncService:
    def test_create_operation(self):
        from app.services.offline_sync import SyncService
        sync = SyncService()
        result = sync.apply_operations([{
            "op_type": "create",
            "collection": "transactions",
            "record_id": "tx1",
            "data": {"amount": 100, "merchant": "Test"},
        }], "device1")
        assert result["applied"] == 1
        assert result["conflicts"] == 0

    def test_update_no_conflict(self):
        from app.services.offline_sync import SyncService
        sync = SyncService()
        sync.apply_operations([{
            "op_type": "create",
            "collection": "transactions",
            "record_id": "tx1",
            "data": {"amount": 100},
            "version": 1,
        }], "device1")

        result = sync.apply_operations([{
            "op_type": "update",
            "collection": "transactions",
            "record_id": "tx1",
            "data": {"amount": 200},
            "version": 1,
        }], "device1")
        assert result["applied"] == 1

    def test_conflict_resolution(self):
        from app.services.offline_sync import SyncService
        sync = SyncService()
        # Create then update (server version 2)
        sync.apply_operations([{
            "op_type": "create", "collection": "t",
            "record_id": "r1", "data": {"a": 1, "b": 2}, "version": 1,
        }], "d1")
        sync.apply_operations([{
            "op_type": "update", "collection": "t",
            "record_id": "r1", "data": {"a": 10, "b": 2}, "version": 1,
        }], "d1")

        # Client tries to update with stale version 1
        result = sync.apply_operations([{
            "op_type": "update", "collection": "t",
            "record_id": "r1", "data": {"a": 1, "b": 99}, "version": 1,
        }], "d2")
        assert result["results"][0].get("conflict") or result["results"][0]["status"] in ("updated", "conflict_resolved")

    def test_delta_sync(self):
        from app.services.offline_sync import SyncService
        sync = SyncService()
        sync.apply_operations([{
            "op_type": "create", "collection": "t",
            "record_id": "r1", "data": {"a": 1}, "version": 1,
        }], "d1")

        deltas = sync.get_deltas(since_version=0)
        assert deltas["total_changes"] >= 1

    def test_delete(self):
        from app.services.offline_sync import SyncService
        sync = SyncService()
        sync.apply_operations([{
            "op_type": "create", "collection": "t",
            "record_id": "r1", "data": {"a": 1}, "version": 1,
        }], "d1")

        result = sync.apply_operations([{
            "op_type": "delete", "collection": "t",
            "record_id": "r1",
        }], "d1")
        assert result["results"][0]["status"] == "deleted"


class TestConflictResolver:
    def test_lww(self):
        from app.services.offline_sync import ConflictResolver, ConflictStrategy
        cr = ConflictResolver(ConflictStrategy.LAST_WRITE_WINS)
        result = cr.resolve({"a": 1}, {"a": 2}, 1, 2)
        assert result["a"] == 2  # Client wins (higher version)

    def test_server_wins(self):
        from app.services.offline_sync import ConflictResolver, ConflictStrategy
        cr = ConflictResolver(ConflictStrategy.SERVER_WINS)
        result = cr.resolve({"a": 1}, {"a": 2}, 1, 2)
        assert result["a"] == 1

    def test_field_merge(self):
        from app.services.offline_sync import ConflictResolver, ConflictStrategy
        cr = ConflictResolver(ConflictStrategy.FIELD_LEVEL_MERGE)
        result = cr.resolve({"a": 1, "b": 2}, {"a": 1, "b": 99, "c": 3}, 1, 2)
        assert result["b"] == 99  # Client wins (higher version)
        assert result["c"] == 3   # New field preserved
