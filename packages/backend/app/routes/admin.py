"""
Admin endpoints (Issue #128).

GET /admin/db/indexes — return the index report as JSON (same data as
                        the `flask index-report` CLI command).
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..db.index_report import REQUIRED_INDEXES, check_missing_indexes, get_existing_indexes
from ..extensions import db
from ..models import User

bp = Blueprint("admin", __name__)


def _require_admin():
    """Return (user, error_response) — error_response is None if user is ADMIN."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != "ADMIN":
        return None, (jsonify(error="admin access required"), 403)
    return user, None


@bp.get("/db/indexes")
@jwt_required()
def db_index_report():
    """
    Return the database index health report as JSON.

    Requires ADMIN role.  On non-PostgreSQL engines (e.g. SQLite in tests)
    returns an empty existing list with all REQUIRED_INDEXES flagged as missing.

    Response shape:
        {
          "existing":  ["idx_name", ...],
          "required":  ["idx_name", ...],
          "missing":   ["idx_name", ...],
          "extra":     ["idx_name", ...],
          "healthy":   true|false
        }
    """
    _, err = _require_admin()
    if err:
        return err

    engine = db.engine
    existing = get_existing_indexes(engine)
    missing = check_missing_indexes(engine)
    required_set = set(REQUIRED_INDEXES)
    existing_set = set(existing)

    return jsonify({
        "existing": sorted(existing),
        "required": sorted(REQUIRED_INDEXES),
        "missing": sorted(missing),
        "extra": sorted(existing_set - required_set),
        "healthy": len(missing) == 0,
    })
