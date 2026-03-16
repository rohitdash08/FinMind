"""
Merchant & payee alias management.

Allows users to define a canonical merchant name and attach multiple
aliases (raw payee strings from bank statements / expense notes).
Includes a merge endpoint to combine two merchants and a suggest endpoint
that scans expense notes for potential canonical names.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Merchant, MerchantAlias, Expense

bp = Blueprint("merchants", __name__)


def _serialize(merchant: Merchant) -> dict:
    return {
        "id": merchant.id,
        "canonical_name": merchant.canonical_name,
        "aliases": [
            {"id": a.id, "alias": a.alias, "created_at": a.created_at.isoformat()}
            for a in merchant.aliases
        ],
        "created_at": merchant.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /merchants  — list all merchants for the authenticated user
# ---------------------------------------------------------------------------

@bp.get("")
@jwt_required()
def list_merchants():
    uid = int(get_jwt_identity())
    q = (request.args.get("q") or "").strip().lower()
    query = Merchant.query.filter_by(user_id=uid)
    if q:
        query = query.filter(
            func.lower(Merchant.canonical_name).contains(q)
        )
    merchants = query.order_by(Merchant.canonical_name).all()
    return jsonify([_serialize(m) for m in merchants])


# ---------------------------------------------------------------------------
# POST /merchants  — create a new merchant with optional aliases
# ---------------------------------------------------------------------------

@bp.post("")
@jwt_required()
def create_merchant():
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    canonical_name = (body.get("canonical_name") or "").strip()
    if not canonical_name:
        return jsonify({"error": "canonical_name is required"}), 400

    # Prevent duplicates (case-insensitive) for the same user
    existing = Merchant.query.filter(
        Merchant.user_id == uid,
        func.lower(Merchant.canonical_name) == canonical_name.lower(),
    ).first()
    if existing:
        return jsonify({"error": "Merchant already exists", "merchant": _serialize(existing)}), 409

    merchant = Merchant(user_id=uid, canonical_name=canonical_name)
    db.session.add(merchant)
    db.session.flush()  # get merchant.id before aliases

    for raw_alias in body.get("aliases", []):
        alias_str = (raw_alias or "").strip()
        if alias_str:
            db.session.add(MerchantAlias(merchant_id=merchant.id, alias=alias_str))

    db.session.commit()
    return jsonify(_serialize(merchant)), 201


# ---------------------------------------------------------------------------
# GET /merchants/<id>  — get single merchant
# ---------------------------------------------------------------------------

@bp.get("/<int:mid>")
@jwt_required()
def get_merchant(mid: int):
    uid = int(get_jwt_identity())
    merchant = Merchant.query.filter_by(id=mid, user_id=uid).first_or_404()
    return jsonify(_serialize(merchant))


# ---------------------------------------------------------------------------
# PATCH /merchants/<id>  — update canonical name
# ---------------------------------------------------------------------------

@bp.patch("/<int:mid>")
@jwt_required()
def update_merchant(mid: int):
    uid = int(get_jwt_identity())
    merchant = Merchant.query.filter_by(id=mid, user_id=uid).first_or_404()
    body = request.get_json(silent=True) or {}
    new_name = (body.get("canonical_name") or "").strip()
    if not new_name:
        return jsonify({"error": "canonical_name is required"}), 400
    merchant.canonical_name = new_name
    db.session.commit()
    return jsonify(_serialize(merchant))


# ---------------------------------------------------------------------------
# DELETE /merchants/<id>  — delete merchant (and all its aliases)
# ---------------------------------------------------------------------------

@bp.delete("/<int:mid>")
@jwt_required()
def delete_merchant(mid: int):
    uid = int(get_jwt_identity())
    merchant = Merchant.query.filter_by(id=mid, user_id=uid).first_or_404()
    db.session.delete(merchant)
    db.session.commit()
    return jsonify({"deleted": True})


# ---------------------------------------------------------------------------
# POST /merchants/<id>/aliases  — add alias to merchant
# ---------------------------------------------------------------------------

@bp.post("/<int:mid>/aliases")
@jwt_required()
def add_alias(mid: int):
    uid = int(get_jwt_identity())
    merchant = Merchant.query.filter_by(id=mid, user_id=uid).first_or_404()
    body = request.get_json(silent=True) or {}
    alias_str = (body.get("alias") or "").strip()
    if not alias_str:
        return jsonify({"error": "alias is required"}), 400

    # Prevent duplicate alias on the same merchant
    dup = MerchantAlias.query.filter_by(merchant_id=mid, alias=alias_str).first()
    if dup:
        return jsonify({"error": "Alias already exists on this merchant"}), 409

    alias = MerchantAlias(merchant_id=mid, alias=alias_str)
    db.session.add(alias)
    db.session.commit()
    return jsonify(_serialize(merchant)), 201


# ---------------------------------------------------------------------------
# DELETE /merchants/<id>/aliases/<alias_id>  — remove alias
# ---------------------------------------------------------------------------

@bp.delete("/<int:mid>/aliases/<int:alias_id>")
@jwt_required()
def remove_alias(mid: int, alias_id: int):
    uid = int(get_jwt_identity())
    # Verify ownership via merchant
    merchant = Merchant.query.filter_by(id=mid, user_id=uid).first_or_404()
    alias = MerchantAlias.query.filter_by(id=alias_id, merchant_id=mid).first_or_404()
    db.session.delete(alias)
    db.session.commit()
    return jsonify(_serialize(merchant))


# ---------------------------------------------------------------------------
# POST /merchants/merge  — merge source into target (combine aliases)
# ---------------------------------------------------------------------------

@bp.post("/merge")
@jwt_required()
def merge_merchants():
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    target_id = body.get("target_id")
    source_id = body.get("source_id")
    if not target_id or not source_id:
        return jsonify({"error": "target_id and source_id are required"}), 400
    if target_id == source_id:
        return jsonify({"error": "target_id and source_id must be different"}), 400

    target = Merchant.query.filter_by(id=target_id, user_id=uid).first_or_404()
    source = Merchant.query.filter_by(id=source_id, user_id=uid).first_or_404()

    # Move all aliases from source to target
    for alias in list(source.aliases):
        # Avoid duplicates
        exists = MerchantAlias.query.filter_by(
            merchant_id=target.id, alias=alias.alias
        ).first()
        if not exists:
            alias.merchant_id = target.id

    # Add source canonical name as an alias on target (if not already there)
    canon_as_alias = MerchantAlias.query.filter_by(
        merchant_id=target.id, alias=source.canonical_name
    ).first()
    if not canon_as_alias:
        db.session.add(
            MerchantAlias(merchant_id=target.id, alias=source.canonical_name)
        )

    db.session.delete(source)
    db.session.commit()
    return jsonify(_serialize(target))


# ---------------------------------------------------------------------------
# GET /merchants/suggest?q=  — suggest canonical names from expense notes
# ---------------------------------------------------------------------------

@bp.get("/suggest")
@jwt_required()
def suggest_merchants():
    uid = int(get_jwt_identity())
    q = (request.args.get("q") or "").strip()
    limit = min(20, max(1, int(request.args.get("limit", 10))))

    # Pull distinct non-null notes from expenses that contain the query
    query = (
        db.session.query(Expense.notes)
        .filter(Expense.user_id == uid, Expense.notes.isnot(None))
        .distinct()
    )
    if q:
        query = query.filter(
            func.lower(Expense.notes).contains(q.lower())
        )
    rows = query.limit(limit * 5).all()  # over-fetch, then deduplicate

    # Simple deduplication: return trimmed unique notes as suggestions
    seen: set[str] = set()
    suggestions: list[str] = []
    for (note,) in rows:
        norm = note.strip()
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            suggestions.append(norm)
        if len(suggestions) >= limit:
            break

    return jsonify({"suggestions": suggestions, "query": q})
