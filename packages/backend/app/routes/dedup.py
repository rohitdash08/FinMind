from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.dedup import find_duplicates, resolve_ambiguous
import logging

bp = Blueprint("dedup", __name__)
logger = logging.getLogger("finmind.dedup")


@bp.post("/check")
@jwt_required()
def check_duplicates():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    threshold = float(data.get("threshold", 0.7))
    if not transactions:
        return jsonify(error="transactions required"), 400
    results = find_duplicates(uid, transactions, threshold)
    logger.info("Dedup check user=%s transactions=%d matches=%d", uid, len(transactions), len(results))
    return jsonify(
        total=len(transactions),
        potential_duplicates=len(results),
        results=results,
    )


@bp.post("/resolve")
@jwt_required()
def resolve_duplicates():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    candidates = data.get("candidates", [])
    resolutions = data.get("resolutions", [])
    if not candidates or not resolutions:
        return jsonify(error="candidates and resolutions required"), 400
    result = resolve_ambiguous(uid, candidates, resolutions)
    logger.info("Dedup resolve user=%s result=%s", uid, result)
    return jsonify(result)


@bp.post("/score")
@jwt_required()
def score_pair():
    data = request.get_json() or {}
    a = data.get("a", {})
    b = data.get("b", {})
    if not a or not b:
        return jsonify(error="two transactions required"), 400
    from ..services.dedup import score_similarity
    score = score_similarity(a, b)
    return jsonify(score=score)
