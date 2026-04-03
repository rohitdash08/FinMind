"""
Database indexing performance analysis utilities.
Provides query performance monitoring and index health checks.
Issue #128: Database indexing optimization for financial queries.
"""

from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import jwt_required
from ..extensions import db
from sqlalchemy import text
import logging

bp = Blueprint("performance", __name__)
logger = logging.getLogger("finmind.performance")


def get_index_stats():
    """Get statistics for all FinMind indexes from pg_stat_user_indexes."""
    sql = text("""
        SELECT
            schemaname,
            tablename,
            indexname,
            idx_scan      AS scans,
            idx_tup_read  AS tuples_read,
            idx_tup_fetch AS tuples_fetched
        FROM pg_stat_user_indexes
        WHERE schemaname = 'public'
        ORDER BY idx_scan DESC
    """)
    rows = db.session.execute(sql).fetchall()
    return [
        {
            "table": r.tablename,
            "index": r.indexname,
            "scans": r.scans,
            "tuples_read": r.tuples_read,
            "tuples_fetched": r.tuples_fetched,
        }
        for r in rows
    ]


def get_slow_queries(min_ms: float = 100.0):
    """
    Get slow queries from pg_stat_statements if available.
    Requires pg_stat_statements extension.
    """
    try:
        sql = text("""
            SELECT
                query,
                calls,
                round((mean_exec_time)::numeric, 2) AS mean_ms,
                round((total_exec_time)::numeric, 2) AS total_ms,
                rows
            FROM pg_stat_statements
            WHERE mean_exec_time > :min_ms
              AND query NOT LIKE '%pg_stat%'
            ORDER BY mean_exec_time DESC
            LIMIT 20
        """)
        rows = db.session.execute(sql, {"min_ms": min_ms}).fetchall()
        return [
            {
                "query": r.query[:200],
                "calls": r.calls,
                "mean_ms": float(r.mean_ms),
                "total_ms": float(r.total_ms),
                "rows": r.rows,
            }
            for r in rows
        ]
    except Exception:
        return []


def get_table_bloat():
    """Get approximate table bloat percentages."""
    sql = text("""
        SELECT
            relname AS table_name,
            n_live_tup AS live_rows,
            n_dead_tup AS dead_rows,
            CASE
                WHEN n_live_tup + n_dead_tup > 0
                THEN round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
                ELSE 0
            END AS dead_pct,
            last_autovacuum,
            last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
        ORDER BY n_dead_tup DESC
    """)
    rows = db.session.execute(sql).fetchall()
    return [
        {
            "table": r.table_name,
            "live_rows": r.live_rows,
            "dead_rows": r.dead_rows,
            "dead_pct": float(r.dead_pct),
            "last_autovacuum": str(r.last_autovacuum) if r.last_autovacuum else None,
            "last_autoanalyze": str(r.last_autoanalyze) if r.last_autoanalyze else None,
        }
        for r in rows
    ]


@bp.get("/index-stats")
@jwt_required()
def index_stats():
    """Return index usage statistics (admin use)."""
    try:
        stats = get_index_stats()
        return jsonify({"indexes": stats, "count": len(stats)})
    except Exception as e:
        logger.error("index_stats error: %s", e)
        return jsonify(error="failed to fetch index stats"), 500


@bp.get("/table-health")
@jwt_required()
def table_health():
    """Return table health (bloat, vacuum status)."""
    try:
        bloat = get_table_bloat()
        return jsonify({"tables": bloat})
    except Exception as e:
        logger.error("table_health error: %s", e)
        return jsonify(error="failed to fetch table health"), 500


@bp.get("/slow-queries")
@jwt_required()
def slow_queries():
    """Return slow query analysis from pg_stat_statements."""
    try:
        min_ms = float(request_arg("min_ms", 50.0))
        queries = get_slow_queries(min_ms)
        return jsonify({"queries": queries, "min_ms": min_ms})
    except Exception as e:
        logger.error("slow_queries error: %s", e)
        return jsonify(error="failed to fetch slow queries"), 500


def request_arg(name: str, default):
    """Safe request argument extraction."""
    from flask import request
    val = request.args.get(name)
    if val is None:
        return default
    try:
        return type(default)(val)
    except (ValueError, TypeError):
        return default