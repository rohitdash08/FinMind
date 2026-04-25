"""
智能财务周摘要服务
- 生成每周财务摘要和洞察
- 支持邮件发送
"""
import json
from datetime import datetime, timedelta
from urllib import request
from collections import defaultdict

from sqlalchemy import extract, func, and_

from ..config import Settings
from ..extensions import db
from ..models import Expense, Bill, User

_settings = Settings()
DEFAULT_PERSONA = (
    "You are FinMind's friendly financial coach. Write an engaging, actionable "
    "weekly summary email. Be encouraging, positive, and provide specific "
    "realistic advice. Keep it conversational, not too formal."
)


def _get_week_range(week_start: str) -> tuple[datetime, datetime]:
    """解析周开始日期，返回起止时间"""
    start = datetime.strptime(week_start, "%Y-%m-%d")
    end = start + timedelta(days=6)
    return start, end


def _get_week_data(uid: int, start_date: datetime, end_date: datetime) -> dict:
    """获取一周的财务数据"""
    # 收入和支出
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date.date(),
            Expense.spent_at <= end_date.date(),
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )

    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date.date(),
            Expense.spent_at <= end_date.date(),
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    # 按类别统计
    category_rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date.date(),
            Expense.spent_at <= end_date.date(),
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    categories = {str(k or "uncategorized"): float(v) for k, v in category_rows}

    # 交易数量
    transaction_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date.date(),
            Expense.spent_at <= end_date.date(),
        )
        .scalar()
    )

    # 本周到期账单
    upcoming_bills = (
        db.session.query(Bill.name, Bill.amount, Bill.next_due_date)
        .filter(
            Bill.user_id == uid,
            Bill.next_due_date >= start_date.date(),
            Bill.next_due_date <= end_date.date(),
            Bill.active == True,
        )
        .all()
    )

    return {
        "week_start": start_date.strftime("%Y-%m-%d"),
        "week_end": end_date.strftime("%Y-%m-%d"),
        "total_income": float(income or 0),
        "total_expenses": float(expenses or 0),
        "net_flow": float((income or 0) - (expenses or 0)),
        "categories": categories,
        "transaction_count": int(transaction_count or 0),
        "upcoming_bills": [
            {"name": name, "amount": float(amount), "due_date": due_date.isoformat()}
            for name, amount, due_date in upcoming_bills
        ],
    }


def _compare_with_previous_week(
    current_data: dict, previous_data: dict
) -> dict[str, float]:
    """计算与上周的对比变化百分比"""
    result = {}

    for key in ["total_income", "total_expenses", "net_flow"]:
        curr = current_data.get(key, 0)
        prev = previous_data.get(key, 0)
        if prev > 0:
            result[f"{key}_pct_change"] = round(((curr - prev) / prev) * 100, 2)
        else:
            result[f"{key}_pct_change"] = 0.0

    return result


def _extract_json_object(raw: str) -> dict:
    """从 LLM 返回中提取 JSON 对象"""
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


def _generate_gemini_summary(
    week_data: dict, prev_week_data: dict, api_key: str, model: str, persona: str
) -> dict:
    """使用 Gemini 生成智能周摘要"""
    comparison = _compare_with_previous_week(week_data, prev_week_data)

    prompt = f"""{persona}

Generate a weekly financial summary email digest. Return STRICT JSON ONLY with these keys:

1. "subject": string - Email subject line (catchy, personalized)
2. "greeting": string - Friendly opening greeting
3. "highlights": string[] - 2-3 key financial wins/achievements
4. "insights": string[] - 2-3 data-driven insights about spending patterns
5. "warnings": string[] - 0-2 potential issues (overspending, upcoming bills)
6. "tips": string[] - 2-3 actionable, specific recommendations
7. "closing": string - Encouraging closing message

Week Data:
- Week: {week_data['week_start']} to {week_data['week_end']}
- Total Income: ${week_data['total_income']:.2f}
- Total Expenses: ${week_data['total_expenses']:.2f}
- Net Flow: ${week_data['net_flow']:.2f} ({'+' if comparison['net_flow_pct_change'] >= 0 else ''}{comparison['net_flow_pct_change']}% vs last week)
- Expenses change: {'+' if comparison['total_expenses_pct_change'] >= 0 else ''}{comparison['total_expenses_pct_change']}% vs last week
- Transactions: {week_data['transaction_count']}
- Top spending categories: {list(week_data['categories'].items())[:3]}
- Upcoming bills this week: {len(week_data['upcoming_bills'])} bills totaling ${sum(b['amount'] for b in week_data['upcoming_bills']):.2f}

Return ONLY the JSON object, no other text.
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
    ).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return _extract_json_object(text)


def _heuristic_summary(week_data: dict, prev_week_data: dict) -> dict:
    """纯启发式摘要（无 API key 时使用）"""
    comparison = _compare_with_previous_week(week_data, prev_week_data)

    net_flow = week_data["net_flow"]
    expenses_pct = comparison["total_expenses_pct_change"]

    highlights = []
    if net_flow > 0:
        highlights.append(f"Great week! You saved ${net_flow:.2f} this week! 🎉")
    else:
        highlights.append(f"Net flow was ${abs(net_flow):.2f} this week.")

    if expenses_pct < 0:
        highlights.append(f"Spending decreased by {abs(expenses_pct)}% vs last week! 📉")
    elif expenses_pct > 0:
        highlights.append(f"Spending increased by {expenses_pct}% vs last week")

    insights = []
    top_categories = list(week_data["categories"].items())[:3]
    for cat_id, amount in top_categories:
        insights.append(f"Highest spend in category {cat_id}: ${amount:.2f}")

    if week_data["upcoming_bills"]:
        total_bills = sum(b["amount"] for b in week_data["upcoming_bills"])
        insights.append(f"{len(week_data['upcoming_bills'])} upcoming bills (${total_bills:.2f} total)")

    return {
        "subject": f"Your Weekly Financial Digest - {week_data['week_start']}",
        "greeting": "Here's your weekly financial summary!",
        "highlights": highlights,
        "insights": insights,
        "warnings": [],
        "tips": [
            "Review top spending categories for potential savings",
            "Set aside funds for upcoming bills early",
        ],
        "closing": "Keep up the good work! 💪",
        "method": "heuristic",
    }


def generate_weekly_summary(
    uid: int,
    week_start: str,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    """
    生成每周财务摘要

    Args:
        uid: 用户 ID
        week_start: 周开始日期 (YYYY-MM-DD)
        gemini_api_key: 可选的 Gemini API key
        gemini_model: 可选的 Gemini 模型名
        persona: 可选的 AI 人设

    Returns:
        包含摘要数据的字典
    """
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    # 获取本周和上周数据
    start, end = _get_week_range(week_start)
    prev_start = start - timedelta(days=7)
    prev_end = end - timedelta(days=7)

    week_data = _get_week_data(uid, start, end)
    prev_week_data = _get_week_data(uid, prev_start, prev_end)

    # 基础数据
    result = {
        "week_start": week_data["week_start"],
        "week_end": week_data["week_end"],
        "week_data": week_data,
        "previous_week_data": prev_week_data,
        "comparison": _compare_with_previous_week(week_data, prev_week_data),
        "persona": persona_text,
    }

    # 尝试使用 AI 生成摘要
    if key:
        try:
            ai_summary = _generate_gemini_summary(
                week_data, prev_week_data, key, model, persona_text
            )
            result.update(ai_summary)
            result["method"] = "gemini"
            return result
        except Exception as e:
            # 失败后降级到启发式
            result["warnings"] = [f"gemini_unavailable: {str(e)}"]
            result.update(_heuristic_summary(week_data, prev_week_data))
            return result

    # 无 API key 时使用启发式
    result.update(_heuristic_summary(week_data, prev_week_data))
    return result


def send_weekly_digest_email(uid: int, week_start: str) -> dict:
    """
    发送周摘要邮件（预留接口，待邮件服务集成）

    当前版本只生成摘要内容，不实际发送邮件
    """
    summary = generate_weekly_summary(uid, week_start)

    user = db.session.query(User).filter(User.id == uid).first()

    # TODO: 集成 SMTP 邮件发送
    # if user and user.email and _settings.smtp_url:
    #     send_email(
    #         to=user.email,
    #         subject=summary["subject"],
    #         body=render_email_template(summary)
    #     )

    return {
        "sent": False,
        "reason": "email_not_configured",
        "summary": summary,
        "recipient": user.email if user else None,
    }


def get_current_week_start() -> str:
    """获取本周一的日期"""
    today = datetime.now()
    # 周一 = 0, 周日 = 6
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)
    return monday.strftime("%Y-%m-%d")
