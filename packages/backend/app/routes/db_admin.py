"""Database indexing management routes."""

from flask import Blueprint, jsonify
from app.extensions import db
from app.services.db_indexing import create_indexes, get_index_sql, analyze_query_performance

bp = Blueprint("db_admin", __name__)


@bp.route("/indexes", methods=["GET"])
def list_indexes():
    """List all recommended indexes and their SQL."""
    return jsonify({"indexes": get_index_sql()})


@bp.route("/indexes/apply", methods=["POST"])
def apply_indexes():
    """Apply all performance indexes to the database."""
    try:
        with db.engine.connect() as conn:
            results = []
            for sql in get_index_sql():
                try:
                    conn.execute(db.text(sql))
                    conn.commit()
                    results.append({"sql": sql, "status": "ok"})
                except Exception as e:
                    if "already exists" in str(e).lower():
                        results.append({"sql": sql, "status": "exists"})
                    else:
                        results.append({"sql": sql, "status": "error", "error": str(e)})
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/analyze", methods=["GET"])
def analyze_performance():
    """Analyze query performance with EXPLAIN."""
    try:
        with db.engine.connect() as conn:
            results = analyze_query_performance(conn)
        return jsonify({"analysis": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
