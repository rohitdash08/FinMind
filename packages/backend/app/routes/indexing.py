"""Routes for database indexing optimization and performance monitoring.

Provides admin endpoints for:
  - Viewing index coverage
  - Analyzing query performance
  - Getting table statistics
  - Running performance benchmarks
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import indexing as svc

bp = Blueprint("indexing", __name__)


@bp.get("/indexes")
@jwt_required()
def list_indexes():
    """List all database indexes across application tables.

    Returns:
        200: Dict of table → indexes
    """
    indexes = svc.get_all_indexes()
    total = sum(len(v) for v in indexes.values())
    return jsonify({
        "total_indexes": total,
        "tables": indexes,
    }), 200


@bp.get("/coverage")
@jwt_required()
def index_coverage():
    """Analyze which common query patterns have index coverage.

    Returns:
        200: Coverage report with covered/missing patterns
    """
    report = svc.analyze_index_coverage()
    return jsonify(report), 200


@bp.get("/statistics")
@jwt_required()
def table_statistics():
    """Get row counts for all application tables.

    Returns:
        200: List of table statistics
    """
    stats = svc.get_table_statistics()
    return jsonify(stats), 200


@bp.post("/benchmark")
@jwt_required()
def run_benchmark():
    """Run common query benchmarks for the current user.

    Returns:
        200: List of benchmark results with execution times
    """
    uid = int(get_jwt_identity())
    results = svc.benchmark_expense_queries(uid)
    return jsonify({
        "user_id": uid,
        "benchmarks": results,
    }), 200
