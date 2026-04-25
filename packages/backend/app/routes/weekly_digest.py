"""
每周财务摘要 API 路由
"""
from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.weekly_digest import (
    generate_weekly_summary,
    get_current_week_start,
    send_weekly_digest_email,
)

bp = Blueprint("weekly_digest", __name__)
logger = logging.getLogger("finmind.weekly_digest")


@bp.get("/weekly-summary")
@jwt_required()
def get_weekly_summary():
    """
    获取每周财务摘要

    Query Parameters:
        week: 周开始日期 (YYYY-MM-DD)，默认本周一
        X-Gemini-Api-Key: 可选的 Gemini API key (Header)
        X-Insight-Persona: 可选的 AI 人设 (Header)

    Returns:
        包含财务数据和 AI 摘要的 JSON
    """
    uid = int(get_jwt_identity())
    week_start = (
        request.args.get("week") or get_current_week_start()
    ).strip()

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    summary = generate_weekly_summary(
        uid,
        week_start,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )

    logger.info("Weekly summary served user=%s week=%s", uid, week_start)
    return jsonify(summary)


@bp.post("/weekly-summary/send-email")
@jwt_required()
def send_summary_email():
    """
    发送周摘要邮件

    Body Parameters:
        week: 周开始日期 (YYYY-MM-DD)，默认本周一

    Returns:
        发送结果
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    week_start = (data.get("week") or get_current_week_start()).strip()

    result = send_weekly_digest_email(uid, week_start)

    logger.info(
        "Weekly digest email request user=%s week=%s sent=%s",
        uid,
        week_start,
        result.get("sent", False),
    )

    return jsonify(result)
