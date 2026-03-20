from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import User
from ..services.db_indexing import run_index_migration, get_index_health

bp = Blueprint("db_indexing", __name__)


def _require_admin(user_id: int) -> bool:
    """Check if user has admin role."""
    user = User.query.get(user_id)
    return user and getattr(user, "role", "") == "ADMIN"


@bp.route("/db/indexes", methods=["GET"])
@jwt_required()
def index_health():
    """
    GET /insights/db/indexes
    Returns current status of all defined database indexes.
    Admin only.
    """
    user_id = get_jwt_identity()
    if not _require_admin(user_id):
        return jsonify({"error": "Admin access required"}), 403

    health = get_index_health()
    return jsonify(health)


@bp.route("/db/indexes/migrate", methods=["POST"])
@jwt_required()
def migrate_indexes():
    """
    POST /insights/db/indexes/migrate
    Apply all missing database indexes. Idempotent.
    Admin only.
    """
    user_id = get_jwt_identity()
    if not _require_admin(user_id):
        return jsonify({"error": "Admin access required"}), 403

    report = run_index_migration()
    return jsonify({
        "total_indexes": report.total_indexes,
        "existing": report.existing,
        "created": report.created,
        "failed": report.failed,
        "generated_at": report.generated_at,
        "indexes": [
            {
                "name": s.name,
                "table": s.table,
                "columns": s.columns,
                "exists": s.exists,
                "rationale": s.rationale,
            }
            for s in report.index_statuses
        ],
    })