from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion, weekly_financial_summary
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Budget suggestion served user=%s month=%s", uid, ym)
    return jsonify(suggestion)


@bp.get("/weekly-summary")
@jwt_required()
def weekly_summary():
    """生成周度财务摘要"""
    uid = int(get_jwt_identity())
    
    # 获取查询参数
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    
    # 如果没有提供日期，使用最近7天
    from datetime import date, timedelta
    if not end_date:
        end_date = date.today().strftime("%Y-%m-%d")
    if not start_date:
        start_dt = date.today() - timedelta(days=7)
        start_date = start_dt.strftime("%Y-%m-%d")
    
    # 获取用户Gemini API key（如果有）
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    
    try:
        # 调用周报摘要服务
        summary = weekly_financial_summary(
            uid,
            start_date,
            end_date,
            gemini_api_key=user_gemini_key,
            persona=persona,
        )
        
        logger.info("Weekly summary served user=%s period=%s to %s", 
                   uid, start_date, end_date)
        return jsonify(summary)
        
    except Exception as e:
        logger.error("Weekly summary failed user=%s error=%s", uid, str(e))
        return jsonify({
            "error": "Failed to generate weekly summary",
            "details": str(e)
        }), 500
