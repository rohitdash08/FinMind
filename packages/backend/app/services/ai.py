import json
from urllib import request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Expense

_settings = Settings()
DEFAULT_PERSONA = (
    "You are FinMind's pragmatic financial coach. Be concise, non-judgmental, "
    "data-driven, and action-oriented. Return actionable, realistic guidance."
)


def _monthly_totals(uid: int, ym: str) -> tuple[float, float]:
    year, month = map(int, ym.split("-"))
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _category_spend(uid: int, ym: str) -> dict[str, float]:
    year, month = map(int, ym.split("-"))
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _previous_month(ym: str) -> str:
    year, month = map(int, ym.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _build_analytics(uid: int, ym: str) -> dict:
    _, current_expenses = _monthly_totals(uid, ym)
    _, prev_expenses = _monthly_totals(uid, _previous_month(ym))
    if prev_expenses > 0:
        mom = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        mom = 0.0
    cats = _category_spend(uid, ym)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
    return {
        "month_over_month_change_pct": mom,
        "current_month_expenses": round(current_expenses, 2),
        "previous_month_expenses": round(prev_expenses, 2),
        "top_categories": [{"category_id": k, "amount": round(v, 2)} for k, v in top],
    }


def _heuristic_budget(
    uid: int, ym: str, persona: str, warnings: list[str] | None = None
):
    income, expenses = _monthly_totals(uid, ym)
    target = round((expenses * 0.9) if expenses else 500.0, 2)
    payload = {
        "month": ym,
        "suggested_total": target,
        "breakdown": {
            "needs": round(target * 0.5, 2),
            "wants": round(target * 0.3, 2),
            "savings": round(target * 0.2, 2),
        },
        "tips": [
            "Cap discretionary spending in the highest category by 10%.",
            "Set one automatic transfer to savings on payday.",
        ],
        "analytics": _build_analytics(uid, ym),
        "persona": persona,
        "method": "heuristic",
    }
    if warnings:
        payload["warnings"] = warnings
    payload["net_flow"] = round(income - expenses, 2)
    return payload


def _extract_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model did not return JSON object")
    return json.loads(text[start : end + 1])


def _gemini_budget_suggestion(
    uid: int, ym: str, api_key: str, model: str, persona: str
) -> dict:
    categories = _category_spend(uid, ym)
    analytics = _build_analytics(uid, ym)
    prompt = (
        f"{persona}\n"
        "Use this month data and return strict JSON only with keys: "
        "suggested_total, breakdown(needs,wants,savings), tips(list <=3).\n"
        f"month={ym}\n"
        f"category_spend={categories}\n"
        f"analytics={analytics}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
    ).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json_object(text)
    parsed["month"] = ym
    parsed["analytics"] = analytics
    parsed["persona"] = persona
    parsed["method"] = "gemini"
    return parsed


def monthly_budget_suggestion(
    uid: int,
    ym: str,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
):
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_budget_suggestion(uid, ym, key, model, persona_text)
        except Exception:
            return _heuristic_budget(
                uid, ym, persona_text, warnings=["gemini_unavailable"]
            )
    return _heuristic_budget(uid, ym, persona_text)

# ============================================================================
# 周报摘要功能
# ============================================================================

def _weekly_totals(uid: int, start_date: str, end_date: str) -> tuple[float, float]:
    """获取周度的收入和支出总额"""
    from sqlalchemy import and_
    from datetime import datetime
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_dt,
            Expense.spent_at <= end_dt,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_dt,
            Expense.spent_at <= end_dt,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    
    return float(income or 0), float(expenses or 0)


def _weekly_category_trends(uid: int, start_date: str, end_date: str) -> dict:
    """获取周度的分类支出趋势"""
    from datetime import datetime, timedelta
    
    trends = {}
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    while current <= end_dt:
        day_str = current.strftime("%Y-%m-%d")
        next_day = current + timedelta(days=1)
        
        daily_expenses = (
            db.session.query(
                Expense.category_id, 
                func.coalesce(func.sum(Expense.amount), 0)
            )
            .filter(
                Expense.user_id == uid,
                Expense.spent_at >= current,
                Expense.spent_at < next_day,
                Expense.expense_type != "INCOME",
            )
            .group_by(Expense.category_id)
            .all()
        )
        
        trends[day_str] = {str(k or "uncat"): float(v) for k, v in daily_expenses}
        current = next_day
    
    return trends


def weekly_financial_summary(
    uid: int,
    start_date: str,
    end_date: str,
    gemini_api_key: str | None = None,
    persona: str | None = None,
) -> dict:
    """生成周度财务摘要"""
    from datetime import datetime, timedelta
    
    # 获取数据
    weekly_income, weekly_expenses = _weekly_totals(uid, start_date, end_date)
    category_trends = _weekly_category_trends(uid, start_date, end_date)
    
    # 计算趋势（与前一周比较）
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days_diff = (end_dt - start_dt).days + 1
        
        prev_start = (start_dt - timedelta(days=days_diff)).strftime("%Y-%m-%d")
        prev_end = (end_dt - timedelta(days=days_diff)).strftime("%Y-%m-%d")
        prev_income, prev_expenses = _weekly_totals(uid, prev_start, prev_end)
    except:
        prev_income, prev_expenses = 0, 0
    
    # 计算变化百分比
    income_change_pct = 0.0
    if prev_income > 0:
        income_change_pct = round(((weekly_income - prev_income) / prev_income) * 100, 2)
    
    expenses_change_pct = 0.0
    if prev_expenses > 0:
        expenses_change_pct = round(((weekly_expenses - prev_expenses) / prev_expenses) * 100, 2)
    
    # 找出最高支出日和类别
    max_spend_day = None
    max_spend_amount = 0
    top_category = None
    top_category_amount = 0
    
    category_totals = {}
    for day, categories in category_trends.items():
        day_total = sum(categories.values())
        if day_total > max_spend_amount:
            max_spend_amount = day_total
            max_spend_day = day
        
        for category, amount in categories.items():
            category_totals[category] = category_totals.get(category, 0) + amount
            if amount > top_category_amount:
                top_category_amount = amount
                top_category = category
    
    # 基础摘要
    summary = {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "previous_period": {"start": prev_start, "end": prev_end} if prev_income > 0 or prev_expenses > 0 else None
        },
        "totals": {
            "income": round(weekly_income, 2),
            "expenses": round(weekly_expenses, 2),
            "net_flow": round(weekly_income - weekly_expenses, 2),
            "savings_rate": round(((weekly_income - weekly_expenses) / weekly_income * 100), 2) if weekly_income > 0 else 0.0
        },
        "trends": {
            "income_change_pct": income_change_pct,
            "expenses_change_pct": expenses_change_pct,
            "max_spend_day": max_spend_day,
            "max_spend_amount": round(max_spend_amount, 2) if max_spend_amount else 0,
            "top_category": top_category,
            "top_category_amount": round(top_category_amount, 2) if top_category_amount else 0
        },
        "daily_breakdown": {
            day: {
                "total": round(sum(categories.values()), 2),
                "categories": {cat: round(amt, 2) for cat, amt in categories.items()}
            }
            for day, categories in category_trends.items()
        },
        "category_summary": {
            category: round(total, 2)
            for category, total in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        }
    }
    
    # 生成洞察
    summary["insights"] = _generate_weekly_insights_heuristic(summary)
    summary["method"] = "heuristic"
    
    # 如果有Gemini API，可以添加AI洞察
    if gemini_api_key:
        summary["method"] = "ai_enhanced"
        # 这里可以调用AI生成更深入的洞察
    
    return summary


def _generate_weekly_insights_heuristic(summary: dict) -> dict:
    """启发式周报洞察生成"""
    insights = []
    recommendations = []
    
    # 储蓄率分析
    savings_rate = summary["totals"]["savings_rate"]
    if savings_rate > 20:
        insights.append(f"优秀储蓄习惯！本周储蓄率达到{savings_rate}%")
        recommendations.append("继续保持当前储蓄节奏")
    elif savings_rate > 0:
        insights.append(f"储蓄率{savings_rate}%，有进步空间")
        recommendations.append("考虑减少非必要支出，提高储蓄率")
    else:
        insights.append("本周支出超过收入，需要关注现金流")
        recommendations.append("检查大额支出项目，制定预算计划")
    
    # 支出趋势分析
    expenses_change = summary["trends"]["expenses_change_pct"]
    if expenses_change > 15:
        insights.append(f"支出较上周增长{expenses_change}%，注意控制消费")
        recommendations.append("回顾高增长支出类别，设置预算限制")
    elif expenses_change < -10:
        insights.append(f"支出下降{abs(expenses_change)}%，节省效果明显")
        recommendations.append("继续保持节约习惯")
    
    # 最高支出日提醒
    max_day = summary["trends"]["max_spend_day"]
    if max_day:
        insights.append(f"{max_day}是本周支出最高日")
        recommendations.append(f"回顾{max_day}的消费决策")
    
    # 分类建议
    top_cat = summary["trends"]["top_category"]
    if top_cat and top_cat != "uncat":
        insights.append(f"'{top_cat}'类别支出最多")
        recommendations.append(f"为'{top_cat}'类别设置专项预算")
    
    return {
        "key_insights": insights[:4],  # 最多4个关键洞察
        "recommendations": recommendations[:3],  # 最多3个建议
        "summary": "基于本周财务数据的自动化分析"
    }
