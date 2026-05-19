"""API routes for bank sync connectors."""

from flask import Blueprint, jsonify, request

from app.connectors import ConnectorManager, MockBankConnector
from app.connectors.manager import get_connector_manager

connectors_bp = Blueprint("connectors", __name__, url_prefix="/api/connectors")


def _ensure_mock_registered():
    """Register the mock connector on first use."""
    manager = get_connector_manager()
    if "mock" not in manager._connectors:
        manager.register(MockBankConnector())


@connectors_bp.route("/", methods=["GET"])
def list_connectors():
    """List all registered bank connectors."""
    _ensure_mock_registered()
    manager = get_connector_manager()
    return jsonify({"connectors": manager.list_connectors()})


@connectors_bp.route("/<name>/status", methods=["GET"])
def connector_status(name: str):
    """Get connection status for a specific connector."""
    manager = get_connector_manager()
    connector = manager.get(name)
    if connector is None:
        return jsonify({"error": f"Unknown connector: {name}"}), 404
    return jsonify(connector.get_connection_status())


@connectors_bp.route("/<name>/import", methods=["POST"])
async def import_transactions(name: str):
    """Import transactions from a bank connector."""
    _ensure_mock_registered()
    manager = get_connector_manager()

    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id", 1)
    from_date = body.get("from_date")
    to_date = body.get("to_date")

    try:
        transactions = await manager.import_transactions(
            connector_name=name,
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
        )
        return jsonify({
            "connector": name,
            "count": len(transactions),
            "transactions": [
                {
                    "date": str(t.date),
                    "amount": str(t.amount),
                    "description": t.description,
                    "type": t.transaction_type.value,
                    "category_hint": t.category_hint,
                }
                for t in transactions
            ],
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@connectors_bp.route("/<name>/refresh", methods=["POST"])
async def refresh_connection(name: str):
    """Refresh a connector and re-import latest transactions."""
    _ensure_mock_registered()
    manager = get_connector_manager()

    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id", 1)

    try:
        transactions = await manager.refresh(
            connector_name=name,
            user_id=user_id,
        )
        return jsonify({
            "connector": name,
            "healthy": True,
            "count": len(transactions),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except ConnectionError as e:
        return jsonify({"error": str(e), "healthy": False}), 502
