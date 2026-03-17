"""
Offline-First Sync routes (Issue #98).

Endpoints:
  POST /sync/push          — submit a batch of offline operations
  GET  /sync/pull          — fetch incremental delta since last checkpoint
  GET  /sync/status        — return this client's checkpoint info
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.sync_engine import process_sync_batch, pull_delta

bp = Blueprint("sync", __name__)
logger = logging.getLogger("finmind.sync")


@bp.post("/push")
@jwt_required()
def push():
    """
    Submit a batch of offline operations for processing.

    Request body (JSON):
        client_id  (str, required) — opaque device identifier
        operations (list, required) — list of operation objects:
            op          (str) — CREATE | UPDATE | DELETE
            resource    (str) — expense | category
            resource_id (int) — required for UPDATE / DELETE
            client_ts   (str) — ISO timestamp of when the op was recorded offline
            client_seq  (int) — monotonic sequence number (for ordering)
            payload     (dict) — the mutation data

    Response:
        results   — per-operation outcome list
        applied   — int
        conflicts — int
        errors    — int

    Conflict semantics (Last-Write-Wins by client_ts):
        If the server copy was modified AFTER client_ts the operation is
        rejected with status='conflict' and the current server state is
        returned so the client can reconcile.
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    client_id = str(data.get("client_id") or "").strip()
    if not client_id:
        return jsonify(error="client_id is required"), 400

    operations = data.get("operations")
    if not isinstance(operations, list):
        return jsonify(error="'operations' must be a list"), 400

    if len(operations) > 500:
        return jsonify(error="maximum 500 operations per batch"), 400

    result = process_sync_batch(uid, client_id, operations)

    if "error" in result:
        return jsonify(result), 500

    status_code = 200
    return jsonify(result), status_code


@bp.get("/pull")
@jwt_required()
def pull():
    """
    Fetch incremental delta: all server-side changes since the client's
    last known sequence number.

    Query params:
        client_id  (str, required) — same opaque device identifier used in /push
        since_seq  (int, default 0) — last server_seq the client has seen

    Response:
        expenses  — list of expense objects updated after since_seq
        since_seq — echoed back
        max_seq   — highest server_seq in the response (use as next since_seq)
        count     — number of items returned
    """
    uid = int(get_jwt_identity())

    client_id = request.args.get("client_id", "").strip()
    if not client_id:
        return jsonify(error="client_id is required"), 400

    try:
        since_seq = int(request.args.get("since_seq", 0))
        if since_seq < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="since_seq must be a non-negative integer"), 400

    result = pull_delta(uid, client_id, since_seq)
    return jsonify(result)


@bp.get("/status")
@jwt_required()
def sync_status():
    """
    Return checkpoint information for the given client.

    Query params:
        client_id (str, required)

    Response:
        client_id, last_seq, updated_at
    """
    uid = int(get_jwt_identity())

    client_id = request.args.get("client_id", "").strip()
    if not client_id:
        return jsonify(error="client_id is required"), 400

    from sqlalchemy import text
    try:
        row = db_row = None
        from ..extensions import db
        row = db.session.execute(
            text("SELECT last_seq, updated_at FROM sync_checkpoints WHERE user_id=:u AND client_id=:c"),
            {"u": uid, "c": client_id},
        ).fetchone()
    except Exception:
        pass

    if row:
        return jsonify({
            "client_id": client_id,
            "last_seq": row[0],
            "updated_at": row[1].isoformat() if row[1] else None,
        })

    return jsonify({"client_id": client_id, "last_seq": 0, "updated_at": None})
