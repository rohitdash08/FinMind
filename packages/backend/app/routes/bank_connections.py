"""
Bank Connections API.

Provides REST endpoints for managing pluggable bank connectors:
- List available connectors
- Create / delete a bank connection for the authenticated user
- Trigger full imports or incremental refreshes
- View import history
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import BankConnection, BankImportRun
from ..services.bank_connectors import connector_registry
from ..services.bank_connectors.service import BankConnectionService
from ..services.bank_connectors.base import (
    AuthenticationError,
    ConnectorError,
    RateLimitError,
)
from ..services.bank_connectors.registry import ConnectorNotFoundError

bp = Blueprint("bank_connections", __name__)

# ---------------------------------------------------------------------------
# Service instance (lazily created to avoid circular imports at module load)
# ---------------------------------------------------------------------------


def _service() -> BankConnectionService:
    return BankConnectionService(connector_registry)


# ---------------------------------------------------------------------------
# Connector discovery
# ---------------------------------------------------------------------------


@bp.get("/connectors")
@jwt_required()
def list_connectors():
    """
    Return all registered bank connectors and their metadata.

    Returns a list of connector descriptors including:
    - name: unique identifier for programmatic use
    - display_name: human-readable name for the UI
    - supports_refresh: whether the connector supports incremental refresh
    - supports_oauth: whether the connector uses OAuth authentication
    - website_url: link to the bank's official website
    - icon_url: URL of the bank's icon/logo
    """
    connectors = _service().list_available_connectors()
    return jsonify(connectors)


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


@bp.post("/connections")
@jwt_required()
def create_connection():
    """
    Create a new bank connection for the authenticated user.

    Request body (JSON):
    {
        "connector_name": "mock",
        "config": { ... connector-specific credentials ... },
        "display_name": "My Chase Account",   (optional)
        "institution_name": "Chase Bank"        (optional)
    }

    Returns 201 with the new connection record on success.
    Returns 400 if connector_name is missing or invalid.
    Returns 401/403 on auth errors from the connector.
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    connector_name = data.get("connector_name")
    if not connector_name:
        return jsonify(error="connector_name is required"), 400

    config = data.get("config") or {}
    if not isinstance(config, dict):
        return jsonify(error="config must be an object"), 400

    try:
        conn = _service().connect(
            user_id=uid,
            connector_name=connector_name,
            config=config,
            display_name=data.get("display_name"),
            institution_name=data.get("institution_name"),
        )
    except ConnectorNotFoundError:
        return jsonify(error=f"Unknown connector: {connector_name}"), 400
    except AuthenticationError as exc:
        return jsonify(error=str(exc)), 401
    except ConnectorError as exc:
        return jsonify(error=str(exc)), 400

    return jsonify(_connection_to_dict(conn)), 201


@bp.get("/connections")
@jwt_required()
def list_connections():
    """Return all bank connections for the authenticated user."""
    uid = int(get_jwt_identity())
    connections = _service().list_connections(uid)
    return jsonify([_connection_to_dict(c) for c in connections])


@bp.get("/connections/<int:connection_id>")
@jwt_required()
def get_connection(connection_id: int):
    """Return a single bank connection (must belong to the authenticated user)."""
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_connection_to_dict(conn))


@bp.delete("/connections/<int:connection_id>")
@jwt_required()
def delete_connection(connection_id: int):
    """Delete a bank connection and all associated data."""
    uid = int(get_jwt_identity())
    try:
        _service().disconnect(uid, connection_id)
    except ValueError:
        return jsonify(error="not found"), 404
    return jsonify(message="connection deleted"), 200


@bp.post("/connections/<int:connection_id>/refresh-auth")
@jwt_required()
def refresh_auth(connection_id: int):
    """
    Re-authenticate a bank connection to check its current status.

    Returns the updated connection record. The status field will be
    'active' if auth succeeded or 'error' if it failed.
    """
    uid = int(get_jwt_identity())
    try:
        conn = _service().refresh_auth(uid, connection_id)
    except ValueError:
        return jsonify(error="not found"), 404
    except ConnectorError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(_connection_to_dict(conn))


# ---------------------------------------------------------------------------
# Account listing
# ---------------------------------------------------------------------------


@bp.get("/connections/<int:connection_id>/accounts")
@jwt_required()
def list_connection_accounts(connection_id: int):
    """Return all linked accounts for a bank connection."""
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid:
        return jsonify(error="not found"), 404
    accounts = [
        _account_to_dict(bca) for bca in conn.accounts if bca.is_active
    ]
    return jsonify(accounts)


# ---------------------------------------------------------------------------
# Import / refresh
# ---------------------------------------------------------------------------


@bp.post("/connections/<int:connection_id>/import")
@jwt_required()
def import_transactions(connection_id: int):
    """
    Trigger a full import of transactions from a bank connection.

    Query parameters:
    - account_id: import only this account (optional, default = all accounts)
    - from_date: start date YYYY-MM-DD (optional, default = all history)
    - to_date: end date YYYY-MM-DD (optional, default = today)
    - dry_run: if "true", return preview without committing (default false)

    Request body (JSON, optional):
    {
        "config": { ... temporary config overrides ... }
    }

    Returns 200 with an import summary:
    {
        "connection_id": 1,
        "imported_count": 42,
        "duplicate_count": 3,
        "dry_run": false,
        "accounts": [
            {
                "account_id": 1,
                "account_name": "Checking ****1234",
                "imported_count": 42,
                "duplicate_count": 3,
                "transactions": [...]   (only when dry_run=true)
            }
        ]
    }
    """
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid:
        return jsonify(error="not found"), 404

    account_id = request.args.get("account_id", type=int)
    dry_run = request.args.get("dry_run", "false").lower() in ("true", "1", "yes")

    from_date = None
    to_date = None
    try:
        if request.args.get("from_date"):
            from_date = date.fromisoformat(request.args.get("from_date"))
        if request.args.get("to_date"):
            to_date = date.fromisoformat(request.args.get("to_date"))
    except ValueError:
        return jsonify(error="invalid date format, use YYYY-MM-DD"), 400

    config_override = None
    data = request.get_json(silent=True) or {}
    if data.get("config"):
        config_override = data["config"]

    try:
        if config_override:
            connector = connector_registry.create(
                conn.connector_name,
                {**config_override, "user_id": str(uid)},
            )
        else:
            connector = _service().get_connector_instance(conn, config_override)
    except ConnectorNotFoundError:
        return jsonify(error=f"Unknown connector: {conn.connector_name}"), 400
    except ConnectorError as exc:
        return jsonify(error=str(exc)), 400

    result = _service().import_transactions(
        user_id=uid,
        connection_id=connection_id,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
        dry_run=dry_run,
    )
    return jsonify(result)


@bp.post("/connections/<int:connection_id>/refresh")
@jwt_required()
def refresh_transactions(connection_id: int):
    """
    Incrementally refresh transactions — fetches only new transactions
    since the last import.

    Query parameters:
    - account_id: refresh only this account (optional, default = all accounts)

    Returns the same summary format as /import.
    """
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid:
        return jsonify(error="not found"), 404

    account_id = request.args.get("account_id", type=int)

    try:
        result = _service().refresh_transactions(uid, connection_id, account_id)
    except ConnectorError as exc:
        return jsonify(error=str(exc)), 400

    return jsonify(result)


@bp.get("/connections/<int:connection_id>/import-runs")
@jwt_required()
def list_import_runs(connection_id: int):
    """Return recent import run history for a connection."""
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid:
        return jsonify(error="not found"), 404

    limit = request.args.get("limit", 20, type=int)
    runs = _service().list_import_runs(uid, connection_id, limit=limit)
    return jsonify([_run_to_dict(r) for r in runs])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _connection_to_dict(conn: BankConnection) -> dict:
    return {
        "id": conn.id,
        "connector_name": conn.connector_name,
        "display_name": conn.display_name,
        "status": conn.status,
        "institution_name": conn.institution_name,
        "last_refresh_at": (
            conn.last_refresh_at.isoformat() if conn.last_refresh_at else None
        ),
        "last_error": conn.last_error,
        "created_at": conn.created_at.isoformat(),
        "updated_at": conn.updated_at.isoformat(),
        "accounts": [
            _account_to_dict(bca) for bca in conn.accounts if bca.is_active
        ],
    }


def _account_to_dict(bca) -> dict:
    return {
        "id": bca.id,
        "external_account_id": bca.external_account_id,
        "account_name": bca.account_name,
        "account_type": bca.account_type,
        "currency": bca.currency,
        "current_balance": (
            float(bca.current_balance) if bca.current_balance else None
        ),
        "mask": bca.mask,
        "is_active": bca.is_active,
        "metadata": bca.metadata_json or {},
    }


def _run_to_dict(run: BankImportRun) -> dict:
    return {
        "id": run.id,
        "bank_connection_id": run.bank_connection_id,
        "account_id": run.account_id,
        "imported_count": run.imported_count,
        "duplicate_count": run.duplicate_count,
        "status": run.status,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat(),
        "completed_at": (
            run.completed_at.isoformat() if run.completed_at else None
        ),
    }
