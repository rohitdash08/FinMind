"""
Offline-First Sync Engine (Issue #98).

Processes a batch of offline operations (sync queue) submitted by a client,
applies them to the database with conflict detection, and returns both the
result per operation and the incremental delta the client needs to catch up.

Conflict resolution strategy: Last-Write-Wins by client_ts (timestamp).
If a resource was modified on the server AFTER client_ts, the server version
wins and the operation is marked 'conflict'.  The client receives the current
server state so it can reconcile locally.

Public API
----------
process_sync_batch(uid, client_id, operations) → SyncResult
pull_delta(uid, client_id, since_seq)          → DeltaResult
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..extensions import db
from ..models import Category, Expense, User

logger = logging.getLogger("finmind.sync")

# ── Types ─────────────────────────────────────────────────────────────────────

VALID_OPERATIONS   = frozenset(["CREATE", "UPDATE", "DELETE"])
VALID_RESOURCES    = frozenset(["expense", "category"])
CONFLICT_WINDOW_S  = 0  # seconds; server_updated_at > client_ts → conflict


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


# ── Conflict detection ────────────────────────────────────────────────────────

def _expense_updated_at(expense: Expense) -> datetime:
    """Return the server-side last-modified timestamp for an expense."""
    ts = expense.created_at  # Expense has no updated_at in base schema
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _has_conflict(server_ts: datetime, client_ts: datetime) -> bool:
    """True when the server version is strictly newer than the client timestamp."""
    return server_ts > client_ts


# ── Operation handlers ────────────────────────────────────────────────────────

def _apply_expense_create(uid: int, payload: dict, client_ts: datetime) -> tuple[str, dict]:
    """Create an expense from a client payload. Returns (status, result)."""
    from decimal import Decimal, InvalidOperation
    from datetime import date as date_type

    try:
        amount = Decimal(str(payload.get("amount", 0)))
        if amount <= 0:
            return "error", {"error": "amount must be positive"}
    except (InvalidOperation, ValueError):
        return "error", {"error": "invalid amount"}

    spent_raw = payload.get("spent_at") or payload.get("date")
    try:
        spent = date_type.fromisoformat(spent_raw) if spent_raw else date_type.today()
    except (ValueError, TypeError):
        spent = date_type.today()

    expense = Expense(
        user_id=uid,
        category_id=payload.get("category_id"),
        amount=amount,
        currency=str(payload.get("currency", "INR"))[:10].upper(),
        expense_type=str(payload.get("expense_type", "EXPENSE")).upper(),
        notes=str(payload.get("notes", ""))[:500] or None,
        spent_at=spent,
    )
    db.session.add(expense)
    db.session.flush()
    return "applied", {"server_id": expense.id}


def _apply_expense_update(uid: int, resource_id: int, payload: dict, client_ts: datetime) -> tuple[str, dict]:
    """Update an expense. Detects conflicts."""
    expense = db.session.get(Expense, resource_id)
    if not expense or expense.user_id != uid:
        return "error", {"error": "not found"}

    server_ts = _expense_updated_at(expense)
    if _has_conflict(server_ts, client_ts):
        return "conflict", {
            "reason": "server_newer",
            "server_ts": server_ts.isoformat(),
            "client_ts": client_ts.isoformat(),
            "server_state": {
                "id": expense.id,
                "amount": float(expense.amount),
                "notes": expense.notes,
                "spent_at": expense.spent_at.isoformat() if expense.spent_at else None,
                "expense_type": expense.expense_type,
            },
        }

    from decimal import Decimal, InvalidOperation
    if "amount" in payload:
        try:
            expense.amount = Decimal(str(payload["amount"]))
        except InvalidOperation:
            return "error", {"error": "invalid amount"}
    if "notes" in payload:
        expense.notes = str(payload["notes"])[:500] or None
    if "expense_type" in payload:
        expense.expense_type = str(payload["expense_type"]).upper()
    if "category_id" in payload:
        expense.category_id = payload["category_id"]

    db.session.flush()
    return "applied", {"server_id": expense.id}


def _apply_expense_delete(uid: int, resource_id: int, client_ts: datetime) -> tuple[str, dict]:
    """Delete an expense. Detects conflicts."""
    expense = db.session.get(Expense, resource_id)
    if not expense or expense.user_id != uid:
        # Idempotent: already gone is fine
        return "applied", {"server_id": resource_id}

    server_ts = _expense_updated_at(expense)
    if _has_conflict(server_ts, client_ts):
        return "conflict", {
            "reason": "server_newer",
            "server_ts": server_ts.isoformat(),
            "client_ts": client_ts.isoformat(),
        }

    db.session.delete(expense)
    db.session.flush()
    return "applied", {"server_id": resource_id}


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def _get_or_create_checkpoint(uid: int, client_id: str) -> Any:
    """Return the SyncCheckpoint row for (uid, client_id), creating it if needed."""
    from sqlalchemy import text
    row = db.session.execute(
        text("SELECT id, last_seq FROM sync_checkpoints WHERE user_id=:u AND client_id=:c"),
        {"u": uid, "c": client_id},
    ).fetchone()
    if row is None:
        db.session.execute(
            text("INSERT INTO sync_checkpoints (user_id, client_id, last_seq) VALUES (:u, :c, 0)"),
            {"u": uid, "c": client_id},
        )
        db.session.flush()
        return {"id": None, "last_seq": 0}
    return {"id": row[0], "last_seq": row[1]}


def _update_checkpoint(uid: int, client_id: str, new_seq: int) -> None:
    from sqlalchemy import text
    db.session.execute(
        text(
            "INSERT INTO sync_checkpoints (user_id, client_id, last_seq, updated_at) "
            "VALUES (:u, :c, :seq, NOW()) "
            "ON CONFLICT (user_id, client_id) DO UPDATE SET last_seq=:seq, updated_at=NOW()"
        ),
        {"u": uid, "c": client_id, "seq": new_seq},
    )


# ── Public API ────────────────────────────────────────────────────────────────

def process_sync_batch(
    uid: int,
    client_id: str,
    operations: list[dict],
) -> dict[str, Any]:
    """
    Process a batch of offline operations submitted by a client.

    Each operation dict must have:
        op          (str)  — CREATE | UPDATE | DELETE
        resource    (str)  — expense | category
        resource_id (int)  — required for UPDATE / DELETE
        client_ts   (str)  — ISO timestamp when the op was recorded
        payload     (dict) — the mutation data

    Returns:
        results    — list of per-operation outcomes
        applied    — count successfully applied
        conflicts  — count of conflict-detected ops
        errors     — count of invalid ops
    """
    if not isinstance(operations, list):
        return {"error": "operations must be a list"}

    results = []
    applied = conflicts = errors = 0

    for op in operations:
        op_type    = str(op.get("op", "")).upper()
        resource   = str(op.get("resource", "")).lower()
        resource_id = op.get("resource_id")
        client_ts  = _parse_ts(op.get("client_ts")) or _utcnow()
        payload    = op.get("payload") or {}
        client_seq = op.get("client_seq")

        if op_type not in VALID_OPERATIONS:
            results.append({"client_seq": client_seq, "status": "error", "error": f"unknown op '{op_type}'"})
            errors += 1
            continue

        if resource not in VALID_RESOURCES:
            results.append({"client_seq": client_seq, "status": "error", "error": f"unsupported resource '{resource}'"})
            errors += 1
            continue

        try:
            if resource == "expense":
                if op_type == "CREATE":
                    status, info = _apply_expense_create(uid, payload, client_ts)
                elif op_type == "UPDATE":
                    if not resource_id:
                        status, info = "error", {"error": "resource_id required for UPDATE"}
                    else:
                        status, info = _apply_expense_update(uid, int(resource_id), payload, client_ts)
                else:  # DELETE
                    if not resource_id:
                        status, info = "error", {"error": "resource_id required for DELETE"}
                    else:
                        status, info = _apply_expense_delete(uid, int(resource_id), payload, client_ts)
            else:
                status, info = "error", {"error": f"resource '{resource}' not yet supported"}

            if status == "applied":
                applied += 1
            elif status == "conflict":
                conflicts += 1
            else:
                errors += 1

            results.append({"client_seq": client_seq, "status": status, **info})

        except Exception as exc:
            logger.warning("sync op failed uid=%s op=%s resource=%s id=%s: %s", uid, op_type, resource, resource_id, exc)
            db.session.rollback()
            results.append({"client_seq": client_seq, "status": "error", "error": str(exc)})
            errors += 1

    try:
        db.session.commit()
    except Exception as exc:
        logger.error("sync batch commit failed uid=%s: %s", uid, exc)
        db.session.rollback()
        return {"error": "batch commit failed", "detail": str(exc)}

    logger.info("sync batch uid=%s client=%s applied=%d conflicts=%d errors=%d",
                uid, client_id, applied, conflicts, errors)

    return {
        "results": results,
        "applied": applied,
        "conflicts": conflicts,
        "errors": errors,
    }


def pull_delta(uid: int, client_id: str, since_seq: int = 0) -> dict[str, Any]:
    """
    Return all expenses modified after *since_seq* (server_seq) for *uid*.

    On databases without the server_seq column (SQLite in tests), falls back
    to returning all expenses for the user.
    """
    from sqlalchemy import text, inspect as sa_inspect

    # Check if server_seq column exists (not present on SQLite test DB)
    try:
        cols = [c["name"] for c in sa_inspect(db.engine).get_columns("expenses")]
        has_seq = "server_seq" in cols
    except Exception:
        has_seq = False

    if has_seq:
        rows = db.session.execute(
            text(
                "SELECT id, user_id, category_id, amount, currency, expense_type, "
                "notes, spent_at, created_at, server_seq "
                "FROM expenses WHERE user_id=:u AND server_seq > :seq ORDER BY server_seq"
            ),
            {"u": uid, "seq": since_seq},
        ).fetchall()
        max_seq = max((r[9] for r in rows), default=since_seq)
    else:
        rows = db.session.execute(
            text(
                "SELECT id, user_id, category_id, amount, currency, expense_type, "
                "notes, spent_at, created_at FROM expenses WHERE user_id=:u ORDER BY id"
            ),
            {"u": uid},
        ).fetchall()
        max_seq = 0

    expenses = []
    for r in rows:
        expenses.append({
            "id": r[0],
            "category_id": r[2],
            "amount": float(r[3]),
            "currency": r[4],
            "expense_type": r[5],
            "notes": r[6],
            "spent_at": r[7].isoformat() if r[7] else None,
            "created_at": r[8].isoformat() if r[8] else None,
        })

    # Update checkpoint
    try:
        _update_checkpoint(uid, client_id, max_seq)
        db.session.commit()
    except Exception:
        db.session.rollback()

    logger.info("pull_delta uid=%s client=%s since=%d returned=%d max_seq=%d",
                uid, client_id, since_seq, len(expenses), max_seq)

    return {
        "expenses": expenses,
        "since_seq": since_seq,
        "max_seq": max_seq,
        "count": len(expenses),
    }
