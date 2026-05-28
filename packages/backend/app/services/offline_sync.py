"""Offline-First Sync with Conflict Resolution.

Implements:
- Operation log for offline changes
- Vector clock for causal ordering
- Three merge strategies: LWW, field-level, custom
- Conflict detection and resolution
- Delta sync (only send changes)
"""

import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.sync")


class ConflictStrategy(str, Enum):
    LAST_WRITE_WINS = "lww"
    FIELD_LEVEL_MERGE = "field_merge"
    SERVER_WINS = "server_wins"
    CLIENT_WINS = "client_wins"


class SyncOperation:
    """Represents a single offline operation."""

    def __init__(self, op_type: str, collection: str, record_id: str,
                 data: dict = None, timestamp: float = None, device_id: str = "",
                 version: int = 0):
        self.op_id = str(uuid4())
        self.op_type = op_type  # create, update, delete
        self.collection = collection
        self.record_id = record_id
        self.data = data or {}
        self.timestamp = timestamp or time.time()
        self.device_id = device_id
        self.version = version
        self.vector_clock = {}

    def to_dict(self) -> dict:
        return {
            "op_id": self.op_id,
            "op_type": self.op_type,
            "collection": self.collection,
            "record_id": self.record_id,
            "data": self.data,
            "timestamp": self.timestamp,
            "device_id": self.device_id,
            "version": self.version,
            "vector_clock": self.vector_clock,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SyncOperation":
        op = cls(
            op_type=data.get("op_type", ""),
            collection=data.get("collection", ""),
            record_id=data.get("record_id", ""),
            data=data.get("data", {}),
            timestamp=data.get("timestamp", time.time()),
            device_id=data.get("device_id", ""),
            version=data.get("version", 0),
        )
        op.op_id = data.get("op_id", op.op_id)
        op.vector_clock = data.get("vector_clock", {})
        return op


class VectorClock:
    """Lamport-style vector clock for causal ordering."""

    def __init__(self):
        self._clock = {}

    def increment(self, device_id: str):
        self._clock[device_id] = self._clock.get(device_id, 0) + 1

    def merge(self, other: dict):
        """Merge with another vector clock, taking max of each entry."""
        for device, tick in other.items():
            self._clock[device] = max(self._clock.get(device, 0), tick)

    def happens_before(self, other: dict) -> bool:
        """Check if this clock happens-before another."""
        all_leq = all(self._clock.get(d, 0) <= t for d, t in other.items())
        any_lt = any(self._clock.get(d, 0) < t for d, t in other.items())
        return all_leq and any_lt

    def is_concurrent(self, other: dict) -> bool:
        """Check if two operations are concurrent (conflict)."""
        return not self.happens_before(other) and not VectorClock.from_dict(other).happens_before(self._clock)

    def to_dict(self) -> dict:
        return dict(self._clock)

    @classmethod
    def from_dict(cls, data: dict) -> "VectorClock":
        vc = cls()
        vc._clock = dict(data)
        return vc


class ConflictResolver:
    """Resolves sync conflicts between client and server data."""

    def __init__(self, strategy: ConflictStrategy = ConflictStrategy.FIELD_LEVEL_MERGE):
        self.strategy = strategy

    def resolve(self, server_data: dict, client_data: dict,
                server_version: int, client_version: int) -> dict:
        """Resolve conflict between server and client data."""
        if self.strategy == ConflictStrategy.LAST_WRITE_WINS:
            return self._lww(server_data, client_data, server_version, client_version)
        elif self.strategy == ConflictStrategy.FIELD_LEVEL_MERGE:
            return self._field_merge(server_data, client_data, server_version, client_version)
        elif self.strategy == ConflictStrategy.SERVER_WINS:
            return server_data
        elif self.strategy == ConflictStrategy.CLIENT_WINS:
            return client_data
        else:
            return server_data  # default safe

    def _lww(self, server: dict, client: dict, sv: int, cv: int) -> dict:
        """Last Write Wins - higher version wins."""
        return client if cv > sv else server

    def _field_merge(self, server: dict, client: dict, sv: int, cv: int) -> dict:
        """Field-level merge - merge individual fields, newer version wins per field."""
        merged = dict(server)  # Start with server data

        # Track which fields changed in client
        for key, value in client.items():
            if key.startswith("_"):  # Skip metadata fields
                continue
            server_val = server.get(key)
            # If client has different value, take the one from newer version
            if server_val != value:
                if cv > sv:
                    merged[key] = value
                elif key not in server:
                    merged[key] = value  # New field from client

        merged["_merge_info"] = {
            "strategy": "field_merge",
            "server_version": sv,
            "client_version": cv,
            "merged_at": datetime.now(timezone.utc).isoformat(),
        }
        return merged


class SyncService:
    """Main sync service for offline-first architecture."""

    def __init__(self):
        self._server_state = {}  # record_id -> {data, version, vector_clock}
        self._op_log = []  # chronological operation log
        self._device_clocks = {}  # device_id -> last_seen_clock

    def apply_operations(self, operations: list[dict], device_id: str) -> dict:
        """Apply a batch of offline operations from a device."""
        results = []
        conflicts = []

        for op_data in operations:
            op = SyncOperation.from_dict(op_data)

            if op.op_type == "create":
                result = self._handle_create(op)
            elif op.op_type == "update":
                result = self._handle_update(op, device_id)
                if result.get("conflict"):
                    conflicts.append(result)
            elif op.op_type == "delete":
                result = self._handle_delete(op)
            else:
                result = {"status": "error", "error": f"Unknown op type: {op.op_type}"}

            results.append(result)
            self._op_log.append(op.to_dict())

        # Update device clock
        if operations:
            self._device_clocks[device_id] = time.time()

        return {
            "sync_id": str(uuid4()),
            "applied": len(results),
            "conflicts": len(conflicts),
            "results": results,
            "server_timestamp": time.time(),
        }

    def get_deltas(self, since_version: int = 0, device_id: str = "") -> dict:
        """Get changes since a given version (delta sync)."""
        deltas = [
            op for op in self._op_log
            if op.get("version", 0) > since_version
        ]
        return {
            "deltas": deltas,
            "latest_version": max((op.get("version", 0) for op in self._op_log), default=0),
            "total_changes": len(deltas),
        }

    def _handle_create(self, op: SyncOperation) -> dict:
        record_id = op.record_id or str(uuid4())
        version = 1
        self._server_state[record_id] = {
            "data": op.data,
            "version": version,
            "vector_clock": op.vector_clock,
            "created_at": time.time(),
        }
        return {"status": "created", "record_id": record_id, "version": version}

    def _handle_update(self, op: SyncOperation, device_id: str) -> dict:
        record_id = op.record_id
        existing = self._server_state.get(record_id)

        if not existing:
            return self._handle_create(op)

        server_version = existing["version"]
        client_version = op.version

        if client_version < server_version:
            # Conflict detected
            resolver = ConflictResolver(ConflictStrategy.FIELD_LEVEL_MERGE)
            merged = resolver.resolve(
                existing["data"], op.data,
                server_version, client_version,
            )
            new_version = server_version + 1
            self._server_state[record_id] = {
                "data": merged,
                "version": new_version,
                "vector_clock": existing.get("vector_clock", {}),
            }
            return {
                "status": "conflict_resolved",
                "record_id": record_id,
                "version": new_version,
                "conflict": True,
                "strategy": "field_merge",
            }
        else:
            new_version = server_version + 1
            self._server_state[record_id] = {
                "data": op.data,
                "version": new_version,
                "vector_clock": op.vector_clock,
            }
            return {"status": "updated", "record_id": record_id, "version": new_version}

    def _handle_delete(self, op: SyncOperation) -> dict:
        record_id = op.record_id
        if record_id in self._server_state:
            del self._server_state[record_id]
            return {"status": "deleted", "record_id": record_id}
        return {"status": "not_found", "record_id": record_id}

    def get_server_state(self, collection: str = None) -> dict:
        """Get current server state for full sync."""
        if collection:
            filtered = {
                rid: state for rid, state in self._server_state.items()
            }
        else:
            filtered = self._server_state

        return {
            "records": {rid: s["data"] for rid, s in filtered.items()},
            "versions": {rid: s["version"] for rid, s in filtered.items()},
        }
