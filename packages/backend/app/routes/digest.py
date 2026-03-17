import json
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import WeeklyDigest
from ..services.weekly_digest import generate_weekly_digest, _week_bounds
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_summary():
    """Return the weekly financial summary digest.

    Query params:
        week_of: ISO date (YYYY-MM-DD) within the desired week.
                 Defaults to current week.
    """
    uid = int(get_jwt_identity())
    raw_date = (request.args.get("week_of") or "").strip()

    week_of = None
    if raw_date:
        try:
            week_of = date.fromisoformat(raw_date)
        except ValueError:
            return jsonify(error="invalid date, expected YYYY-MM-DD"), 400

    try:
        digest = generate_weekly_digest(uid, week_of=week_of)
    except Exception:
        logger.exception("Weekly digest generation failed user=%s", uid)
        return jsonify(error="digest generation failed"), 500

    # Persist the digest for history
    try:
        week_start, week_end = _week_bounds(week_of)
        existing = (
            db.session.query(WeeklyDigest)
            .filter_by(user_id=uid, week_start=week_start)
            .first()
        )
        if existing:
            existing.total_income = digest["summary"]["total_income"]
            existing.total_expenses = digest["summary"]["total_expenses"]
            existing.net_flow = digest["summary"]["net_flow"]
            existing.transaction_count = digest["summary"]["transaction_count"]
            existing.payload = json.dumps(digest)
        else:
            record = WeeklyDigest(
                user_id=uid,
                week_start=week_start,
                week_end=week_end,
                total_income=digest["summary"]["total_income"],
                total_expenses=digest["summary"]["total_expenses"],
                net_flow=digest["summary"]["net_flow"],
                transaction_count=digest["summary"]["transaction_count"],
                payload=json.dumps(digest),
            )
            db.session.add(record)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning("Failed to persist weekly digest user=%s", uid, exc_info=True)

    logger.info("Weekly digest served user=%s", uid)
    return jsonify(digest)


@bp.get("/weekly/history")
@jwt_required()
def weekly_history():
    """Return a paginated list of past weekly digest summaries.

    Query params:
        page: Page number (default 1).
        per_page: Results per page (default 12, max 52).
    """
    uid = int(get_jwt_identity())
    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(52, max(1, int(request.args.get("per_page", "12"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    rows = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=uid)
        .order_by(WeeklyDigest.week_start.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    total = (
        db.session.query(db.func.count(WeeklyDigest.id))
        .filter_by(user_id=uid)
        .scalar()
    ) or 0

    return jsonify(
        {
            "page": page,
            "per_page": per_page,
            "total": total,
            "digests": [
                {
                    "id": r.id,
                    "week_start": r.week_start.isoformat(),
                    "week_end": r.week_end.isoformat(),
                    "total_income": float(r.total_income),
                    "total_expenses": float(r.total_expenses),
                    "net_flow": float(r.net_flow),
                    "transaction_count": r.transaction_count,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        }
    )
