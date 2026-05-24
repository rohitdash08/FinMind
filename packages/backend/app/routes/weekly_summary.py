"""
FinMind — Weekly Summary Route

Fixes applied:
  2. X-Gemini-Api-Key header removed — key is server-side only
  6. ref_date validated: future dates rejected with 400
  9. Flask-Limiter rate limiting + Flask-Caching response cache
"""

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import cache, limiter
from ..services.weekly_summary import weekly_summary

bp = Blueprint("weekly_summary", __name__)
logger = logging.getLogger("finmind.weekly_summary")

# ---------------------------------------------------------------------------
# Cache key: scoped to (user_id, ref_date) so users never see each other's data
# ---------------------------------------------------------------------------

def _cache_key() -> str:
    uid = get_jwt_identity()
    ref = request.args.get("ref_date") or date.today().isoformat()
    return f"wsummary:uid={uid}:week={ref}"


# ---------------------------------------------------------------------------
# Fix #6 — ref_date validation helper
# ---------------------------------------------------------------------------

def _parse_ref_date(raw: str | None) -> tuple[date | None, str | None]:
    """Return (date, None) on success or (None, error_message) on failure."""
    if raw is None:
        return date.today(), None
    try:
        ref = date.fromisoformat(raw)
    except ValueError:
        return None, f"Invalid date format: '{raw}'. Use YYYY-MM-DD."
    if ref > date.today():
        return None, "ref_date cannot be in the future."
    return ref, None


# ---------------------------------------------------------------------------
# Route
# Fix #2: X-Gemini-Api-Key header is no longer read or forwarded
# Fix #6: future ref_date → 400
# Fix #9: @limiter.limit + @cache.cached applied
# ---------------------------------------------------------------------------

@bp.get("/weekly-summary")
@jwt_required()
@limiter.limit("20/minute")          # Fix #9 — rate limiting
@cache.cached(                        # Fix #9 — response cache (TTL 1 h)
    timeout=3600,
    key_prefix=_cache_key,
    unless=lambda: request.args.get("no_cache") == "1",
)
def get_weekly_summary():
    uid = int(get_jwt_identity())

    # Fix #6 — validate ref_date
    ref_date, err = _parse_ref_date(request.args.get("ref_date"))
    if err:
        return jsonify({"error": err}), 400

    # Fix #8 — forward Accept-Language for locale-aware AI responses
    locale = _parse_locale(request.headers.get("Accept-Language", "en"))

    # Fix #9 — allow caller to specify a different Gemini model variant,
    # but the API key is never sourced from the request
    user_model = (request.headers.get("X-Gemini-Model") or "").strip() or None

    summary = weekly_summary(
        uid,
        ref_date=ref_date,
        gemini_model=user_model,
        locale=locale,
    )

    logger.info(
        "Weekly summary served uid=%s week=%s method=%s",
        uid,
        ref_date.isoformat(),
        summary.get("method"),
    )
    return jsonify(summary)


# ---------------------------------------------------------------------------
# Locale helper
# ---------------------------------------------------------------------------

_SUPPORTED_LOCALES = {"en", "zh", "es"}


def _parse_locale(accept_language: str) -> str:
    """Extract the best supported locale from an Accept-Language header."""
    for segment in accept_language.split(","):
        lang = segment.split(";")[0].strip().split("-")[0].lower()
        if lang in _SUPPORTED_LOCALES:
            return lang
    return "en"
