"""
Bank Sync Routes

API endpoints for bank connector operations.
"""

from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from app.services.connectors.base import BankConnector
from app.services.connectors.registry import get_connector, list_connectors

bank_sync_bp = Blueprint("bank_sync", __name__)


def _resolve_connector(provider: str) -> BankConnector:
    """Resolve and instantiate a connector from request credentials."""
    connector_cls = get_connector(provider)
    credentials = request.json.get("credentials", {}) if request.is_json else {}
    return connector_cls(credentials=credentials)


@bank_sync_bp.route("/api/bank-sync/connectors", methods=["GET"])
def list_available_connectors():
    """List all registered bank connectors."""
    connectors = list_connectors()
    return jsonify({"connectors": connectors, "total": len(connectors)})


@bank_sync_bp.route("/api/bank-sync/accounts", methods=["GET"])
async def list_accounts():
    """List bank accounts for a given provider."""
    provider = request.args.get("provider", "mock")
    try:
        connector = _resolve_connector(provider)
        accounts = await connector.get_accounts()
        return jsonify({
            "provider": provider,
            "accounts": [
                {
                    "account_id": a.account_id,
                    "name": a.name,
                    "type": a.type,
                    "balance": a.balance,
                    "currency": a.currency,
                    "masked_number": a.masked_number,
                }
                for a in accounts
            ],
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bank_sync_bp.route("/api/bank-sync/import", methods=["POST"])
async def import_transactions():
    """
    Bulk import transactions for a bank account.

    Request body:
    {
        "provider": "mock",
        "account_id": "mock-checking-001",
        "start_date": "2025-01-01",
        "end_date": "2025-06-02",
        "credentials": {}
    }
    """
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "mock")
    account_id = data.get("account_id")

    if not account_id:
        return jsonify({"error": "account_id is required"}), 400

    try:
        connector = _resolve_connector(provider)
        await connector.connect()

        start_date = None
        end_date = None
        if data.get("start_date"):
            start_date = date.fromisoformat(data["start_date"])
        if data.get("end_date"):
            end_date = date.fromisoformat(data["end_date"])

        result = await connector.import_transactions(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Return transactions for mock provider
        txn_list = []
        if provider == "mock":
            from app.services.connectors.mock_connector import (
                _generate_transactions,
            )
            seed = hash(account_id) % 10000
            sd = start_date or (end_date or date.today()) - timedelta(days=90)
            ed = end_date or date.today()
            transactions = _generate_transactions(sd, ed, seed=seed)
            txn_list = [t.to_import_dict() for t in transactions]

        return jsonify({
            "status": result.status,
            "provider": result.provider,
            "transactions_imported": result.transactions_imported,
            "transactions_skipped": result.transactions_skipped,
            "transactions": txn_list,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bank_sync_bp.route("/api/bank-sync/refresh", methods=["POST"])
async def refresh_transactions():
    """
    Incremental refresh — fetch new/updated transactions.

    Request body:
    {
        "provider": "mock",
        "account_id": "mock-checking-001",
        "since": "2025-05-26",
        "credentials": {}
    }
    """
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "mock")
    account_id = data.get("account_id")

    if not account_id:
        return jsonify({"error": "account_id is required"}), 400

    try:
        connector = _resolve_connector(provider)
        await connector.connect()

        since = None
        if data.get("since"):
            since = date.fromisoformat(data["since"])

        result = await connector.refresh(account_id=account_id, since=since)

        return jsonify({
            "status": result.status,
            "provider": result.provider,
            "transactions_imported": result.transactions_imported,
            "transactions_skipped": result.transactions_skipped,
            "error": result.error,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bank_sync_bp.route("/api/bank-sync/health", methods=["GET"])
async def health_check():
    """Health check for a specific connector."""
    provider = request.args.get("provider", "mock")
    try:
        connector = _resolve_connector(provider)
        health = await connector.health_check()
        return jsonify(health)
    except ValueError as e:
        return jsonify({
            "provider": provider,
            "status": "error",
            "healthy": False,
            "error": str(e),
        }), 400
