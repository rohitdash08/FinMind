from __future__ import annotations

"""
Offline-First Sync with Conflict Resolution (Issue #98)

Strategy: Last-Write-Wins (LWW) with vector-clock-inspired version tracking.
Each record carries a client_version (monotonic counter) and updated_at timestamp.
On sync, the server compares versions and resolves conflicts deterministically.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.models import db, Expense, Income, RecurringBill


class ConflictStrategy(str, Enum):
    LAST_WRITE_WINS = "last_write_wins"
    SERVER_WINS = "server_wins"
    CLIENT_WINS = "client_wins"
    MANUAL = "manual"


class SyncAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    CONFLICT = "conflict"
    SKIPPED = "skipped"


_MODEL_MAP: dict[str, Any] = {
    "expense": Expense,
    "income": Income,
    "recurring_bill": RecurringBill,
}


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ts(dt: datetime | None) -> float:
    """Convert datetime to unix timestamp (0 if None)."""
    if dt is None:
        return 0.0
    if dt.tzinfo is not None:
        return dt.timestamp()
    return dt.replace(tzinfo=timezone.utc).timestamp()


def _newer(server_dt: datetime | None, client_ts: float) -> bool:
    """Return True if server record is strictly newer than client_ts."""
    return _ts(server_dt) > client_ts


# ---------------------------------------------------------------------------
# Core sync engine
# ---------------------------------------------------------------------------

def sync_records(
    uid: int,
    entity_type: str,
    client_records: list[dict],
    strategy: ConflictStrategy = ConflictStrategy.LAST_WRITE_WINS,
) -> dict:
    """
    Synchronise a list of client records with the server database.

    Each client record must contain:
      - id          : server-side id (None / missing for new records)
      - client_id   : stable UUID generated on the client
      - updated_at  : ISO-8601 timestamp of last client modification
      - deleted     : bool (soft-delete flag)
      - payload     : dict of model fields

    Returns a sync report:
      {
        processed: int,
        created: [...],
        updated: [...],
        conflicts: [...],  # only when strategy=manual
        skipped: [...],
        errors: [...],
        server_time: "ISO"
      }
    """
    model = _MODEL_MAP.get(entity_type)
    if model is None:
        raise ValueError(f"Unknown entity_type: {entity_type!r}. Valid: {list(_MODEL_MAP)}")

    report: dict[str, Any] = {
        "processed": len(client_records),
        "created": [],
        "updated": [],
        "conflicts": [],
        "skipped": [],
        "errors": [],
        "server_time": _utc_now().isoformat() + "Z",
    }

    for rec in client_records:
        client_id = rec.get("client_id", "")
        server_id = rec.get("id")
        payload = rec.get("payload", {})
        is_deleted = bool(rec.get("deleted", False))
        try:
            client_updated_ts = _ts(datetime.fromisoformat(rec["updated_at"]))
        except (KeyError, ValueError, TypeError):
            client_updated_ts = 0.0

        try:
            if server_id:
                # Existing record — resolve conflict if needed
                obj = db.session.query(model).filter_by(id=server_id, user_id=uid).first()
                if obj is None:
                    report["errors"].append({"client_id": client_id, "error": "record not found"})
                    continue

                server_ts = _ts(getattr(obj, "updated_at", None))
                conflict = abs(server_ts - client_updated_ts) > 1 and server_ts > client_updated_ts

                if is_deleted:
                    _soft_delete(obj)
                    report["updated"].append({"id": server_id, "action": SyncAction.DELETED})
                elif conflict:
                    action = _resolve_conflict(obj, payload, strategy, client_updated_ts)
                    if action == SyncAction.CONFLICT:
                        report["conflicts"].append({
                            "id": server_id,
                            "client_id": client_id,
                            "server_updated_at": getattr(obj, "updated_at", None),
                            "client_updated_at": rec.get("updated_at"),
                            "server_payload": _to_dict(obj),
                            "client_payload": payload,
                        })
                    else:
                        report["updated"].append({"id": server_id, "action": action})
                else:
                    _apply_payload(obj, payload, uid)
                    report["updated"].append({"id": server_id, "action": SyncAction.UPDATED})

            else:
                # New record — create
                obj = model(user_id=uid)
                _apply_payload(obj, payload, uid)
                db.session.add(obj)
                db.session.flush()  # get id
                report["created"].append({"client_id": client_id, "server_id": obj.id})

        except Exception as exc:
            db.session.rollback()
            report["errors"].append({"client_id": client_id, "error": str(exc)})
            continue

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        report["errors"].append({"error": f"commit failed: {exc}"})

    return report


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------

def _resolve_conflict(
    obj: Any,
    client_payload: dict,
    strategy: ConflictStrategy,
    client_ts: float,
) -> SyncAction:
    """Apply conflict resolution strategy and return resulting action."""
    if strategy == ConflictStrategy.MANUAL:
        return SyncAction.CONFLICT

    if strategy == ConflictStrategy.SERVER_WINS:
        return SyncAction.SKIPPED

    if strategy == ConflictStrategy.CLIENT_WINS:
        _apply_payload(obj, client_payload, obj.user_id)
        return SyncAction.UPDATED

    # Default: LAST_WRITE_WINS
    server_ts = _ts(getattr(obj, "updated_at", None))
    if client_ts >= server_ts:
        _apply_payload(obj, client_payload, obj.user_id)
        return SyncAction.UPDATED
    return SyncAction.SKIPPED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IMMUTABLE = frozenset({"id", "user_id", "created_at"})


def _apply_payload(obj: Any, payload: dict, uid: int) -> None:
    """Write allowed payload fields onto the ORM object."""
    for key, val in payload.items():
        if key in _IMMUTABLE:
            continue
        if hasattr(obj, key):
            setattr(obj, key, val)
    if hasattr(obj, "updated_at"):
        setattr(obj, "updated_at", _utc_now())


def _soft_delete(obj: Any) -> None:
    """Mark record as deleted (soft delete via active/deleted flag)."""
    for flag in ("deleted", "active", "is_active"):
        if hasattr(obj, flag):
            setattr(obj, flag, False if flag in ("active", "is_active") else True)
            break
    if hasattr(obj, "updated_at"):
        setattr(obj, "updated_at", _utc_now())


def _to_dict(obj: Any) -> dict:
    """Convert ORM object to plain dict (column names only)."""
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}


# ---------------------------------------------------------------------------
# Pull endpoint — give clients latest server state since a watermark
# ---------------------------------------------------------------------------

def pull_since(uid: int, entity_type: str, since: datetime | None) -> list[dict]:
    """Return all records of entity_type modified after  for the user."""
    model = _MODEL_MAP.get(entity_type)
    if model is None:
        raise ValueError(f"Unknown entity_type: {entity_type!r}")

    q = db.session.query(model).filter_by(user_id=uid)
    if since and hasattr(model, "updated_at"):
        q = q.filter(model.updated_at > since)
    return [_to_dict(obj) for obj in q.all()]
