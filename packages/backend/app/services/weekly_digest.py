from datetime import date, timedelta
from sqlalchemy import func, extract
from ..extensions import db
from ..models import Expense, Category
from .ai import _extract_json_object, DEFAULT_PERSONA
from ..config import Settings
from urllib import request
import json

_settings = Settings()

def _get_week_data(uid: int, start_date: date, end_date: date):
    expenses = db.session.query(
        Category.name,
        func.sum(Expense.amount).label('total'),
        func.count(Expense.id).label('count')
    ).join(Category, Expense.category_id == Category.id, isouter=True)\
     .filter(
        Expense.user_id == uid,
        Expense.spent_at >= start_date,
        Expense.spent_at <= end_date,
        Expense.expense_type != "INCOME"
    ).group_by(Category.name).all()
    
    return {str(name or "Uncategorized"): {"total": float(total), "count": count} for name, total, count in expenses}

def get_weekly_smart_digest(uid: int, target_date: date = None):
    if not target_date:
        target_date = date.today()
    
    # End of current week is target_date, start is 6 days ago
    curr_end = target_date
    curr_start = curr_end - timedelta(days=6)
    
    # Previous week
    prev_end = curr_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    
    curr_data = _get_week_data(uid, curr_start, curr_end)
    prev_data = _get_week_data(uid, prev_start, prev_end)
    
    curr_total = sum(d['total'] for d in curr_data.values())
    prev_total = sum(d['total'] for d in prev_data.values())
    
    # Identify anomalies and significant deltas
    deltas = []
    all_cats = set(curr_data.keys()) | set(prev_data.keys())
    for cat in all_cats:
        c = curr_data.get(cat, {"total": 0, "count": 0})
        p = prev_data.get(cat, {"total": 0, "count": 0})
        
        if p['total'] > 0:
            diff_pct = ((c['total'] - p['total']) / p['total']) * 100
        else:
            diff_pct = 100.0 if c['total'] > 0 else 0.0
            
        if abs(diff_pct) > 20 or abs(c['total'] - p['total']) > 50:
            deltas.append({
                "category": cat,
                "current": c['total'],
                "previous": p['total'],
                "change_pct": round(diff_pct, 2)
            })

    # AI Integration
    api_key = _settings.gemini_api_key
    model = _settings.gemini_model
    
    digest = {
        "period": f"{curr_start.strftime('%b %d')} - {curr_end.strftime('%b %d')}",
        "total_spend": round(curr_total, 2),
        "prev_total_spend": round(prev_total, 2),
        "total_change_pct": round(((curr_total - prev_total) / prev_total * 100), 2) if prev_total > 0 else 0,
        "significant_changes": deltas,
        "insights": [],
        "prediction": "Steady"
    }

    if api_key:
        prompt = (
            f"{DEFAULT_PERSONA}\n"
            "Analyze this weekly financial data. Focus on WHY spending changed and provide PREDICTIVE warnings.\n"
            "Return strict JSON with keys: insights (list of strings, max 3), prediction (string, short), trend_analysis (string).\n"
            f"Current Week ({digest['period']}): Total {curr_total}, Data: {curr_data}\n"
            f"Previous Week: Total {prev_total}, Data: {prev_data}\n"
            f"Significant Deltas: {deltas}"
        )
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            body = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3}
            }).encode("utf-8")
            req = request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                text = res.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                ai_res = _extract_json_object(text)
                digest["insights"] = ai_res.get("insights", [])
                digest["prediction"] = ai_res.get("prediction", "Unknown")
                digest["trend_analysis"] = ai_res.get("trend_analysis", "")
        except Exception:
            digest["insights"] = ["AI insights temporarily unavailable. Using heuristic analysis."]
            if digest["total_change_pct"] > 10:
                digest["insights"].append("Spending is trending up compared to last week.")
    
    return digest
