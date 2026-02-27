"""Offline-first architecture with sync.

Track local changes, queue sync operations, resolve conflicts,
and maintain sync state between client and server.
"""

import json
from datetime import datetime
from ..extensions import db


class SyncQueue(db.Model):
    __tablename__ = "sync_queue"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)  # expense, category, bill
    entity_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(20), nullable=False)  # create, update, delete
    payload = db.Column(db.Text, default="{}")
    client_timestamp = db.Column(db.DateTime, nullable=False)
    server_timestamp = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending, synced, conflict, failed
    conflict_data = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SyncState(db.Model):
    __tablename__ = "sync_state"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    last_sync = db.Column(db.DateTime, nullable=True)
    sync_token = db.Column(db.String(64), nullable=True)
    version = db.Column(db.Integer, default=0)


ENTITY_TYPES = ["expense", "category", "bill", "budget", "goal"]


def queue_change(user_id: int, entity_type: str, action: str,
                 payload: dict, client_timestamp: datetime,
                 entity_id: int | None = None) -> dict:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown entity type: {entity_type}")
    if action not in ("create", "update", "delete"):
        raise ValueError(f"Invalid action: {action}")

    item = SyncQueue(
        user_id=user_id, entity_type=entity_type, entity_id=entity_id,
        action=action, payload=json.dumps(payload),
        client_timestamp=client_timestamp,
    )
    db.session.add(item)
    db.session.commit()
    return _serialize_queue(item)


def get_pending(user_id: int) -> list[dict]:
    items = (SyncQueue.query.filter_by(user_id=user_id, status="pending")
             .order_by(SyncQueue.client_timestamp).all())
    return [_serialize_queue(i) for i in items]


def sync_batch(user_id: int, changes: list[dict]) -> dict:
    results = []
    conflicts = []
    synced = 0

    for change in changes:
        try:
            item = queue_change(
                user_id, change["entity_type"], change["action"],
                change.get("payload", {}),
                datetime.fromisoformat(change["client_timestamp"]),
                change.get("entity_id"),
            )

            # Check for conflicts (same entity modified)
            existing = SyncQueue.query.filter(
                SyncQueue.user_id == user_id,
                SyncQueue.entity_type == change["entity_type"],
                SyncQueue.entity_id == change.get("entity_id"),
                SyncQueue.id != item["id"],
                SyncQueue.status == "pending",
            ).first()

            if existing and change.get("entity_id"):
                # Conflict: last-write-wins by default
                q = SyncQueue.query.get(item["id"])
                if q:
                    q.status = "conflict"
                    q.conflict_data = json.dumps({"existing_id": existing.id})
                    db.session.commit()
                    conflicts.append(item)
                    continue

            # Mark as synced
            q = SyncQueue.query.get(item["id"])
            if q:
                q.status = "synced"
                q.server_timestamp = datetime.utcnow()
                db.session.commit()
            synced += 1
            results.append(item)

        except (ValueError, KeyError) as e:
            results.append({"error": str(e), "change": change})

    # Update sync state
    state = SyncState.query.filter_by(user_id=user_id).first()
    if not state:
        state = SyncState(user_id=user_id)
        db.session.add(state)
    state.last_sync = datetime.utcnow()
    state.version += 1
    import hashlib
    state.sync_token = hashlib.md5(f"{user_id}:{state.version}".encode()).hexdigest()[:16]
    db.session.commit()

    return {
        "synced": synced, "conflicts": len(conflicts),
        "total": len(changes), "sync_token": state.sync_token,
        "version": state.version,
    }


def get_changes_since(user_id: int, since: datetime | None = None) -> list[dict]:
    q = SyncQueue.query.filter_by(user_id=user_id, status="synced")
    if since:
        q = q.filter(SyncQueue.server_timestamp > since)
    items = q.order_by(SyncQueue.server_timestamp).all()
    return [_serialize_queue(i) for i in items]


def get_conflicts(user_id: int) -> list[dict]:
    items = SyncQueue.query.filter_by(user_id=user_id, status="conflict").all()
    return [_serialize_queue(i) for i in items]


def resolve_conflict(user_id: int, queue_id: int, resolution: str) -> dict:
    item = SyncQueue.query.filter_by(id=queue_id, user_id=user_id, status="conflict").first()
    if not item:
        raise ValueError("Conflict not found")

    if resolution == "accept":
        item.status = "synced"
        item.server_timestamp = datetime.utcnow()
    elif resolution == "reject":
        item.status = "failed"
    else:
        raise ValueError("Resolution must be 'accept' or 'reject'")

    db.session.commit()
    return _serialize_queue(item)


def get_sync_state(user_id: int) -> dict:
    state = SyncState.query.filter_by(user_id=user_id).first()
    if not state:
        return {"last_sync": None, "sync_token": None, "version": 0}
    return {
        "last_sync": state.last_sync.isoformat() if state.last_sync else None,
        "sync_token": state.sync_token, "version": state.version,
    }


def _serialize_queue(item: SyncQueue) -> dict:
    return {
        "id": item.id, "entity_type": item.entity_type,
        "entity_id": item.entity_id, "action": item.action,
        "payload": json.loads(item.payload), "status": item.status,
        "client_timestamp": item.client_timestamp.isoformat(),
        "server_timestamp": item.server_timestamp.isoformat() if item.server_timestamp else None,
    }
