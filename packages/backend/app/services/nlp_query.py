"""
Natural Language Query Service for FinMind
Allows users to query their financial data using natural language.
"""
import json
import re
from datetime import datetime, timedelta
from urllib import request
from typing import Dict, Any, List, Tuple

from sqlalchemy import extract, func, and_, or_
from ..config import Settings
from ..extensions import db
from ..models import Expense, Category

_settings = Settings()


def _parse_date_range(query: str) -> Tuple[datetime, datetime]:
    """
    Extract date range from natural language query.
    Returns (start_date, end_date) tuple.
    """
    query_lower = query.lower()
    today = datetime.now().date()
    
    # Last quarter
    if "last quarter" in query_lower or "previous quarter" in query_lower:
        current_month = today.month
        current_quarter = (current_month - 1) // 3
        if current_quarter == 0:
            # Last quarter of previous year
            start = datetime(today.year - 1, 10, 1).date()
            end = datetime(today.year - 1, 12, 31).date()
        else:
            start_month = (current_quarter - 1) * 3 + 1
            end_month = start_month + 2
            start = datetime(today.year, start_month, 1).date()
            # Last day of end_month
            if end_month == 12:
                end = datetime(today.year, 12, 31).date()
            else:
                end = (datetime(today.year, end_month + 1, 1) - timedelta(days=1)).date()
        return start, end
    
    # This quarter
    if "this quarter" in query_lower or "current quarter" in query_lower:
        current_month = today.month
        current_quarter = (current_month - 1) // 3
        start_month = current_quarter * 3 + 1
        start = datetime(today.year, start_month, 1).date()
        end = today
        return start, end
    
    # Last month
    if "last month" in query_lower or "previous month" in query_lower:
        if today.month == 1:
            start = datetime(today.year - 1, 12, 1).date()
            end = datetime(today.year - 1, 12, 31).date()
        else:
            start = datetime(today.year, today.month - 1, 1).date()
            end = (datetime(today.year, today.month, 1) - timedelta(days=1)).date()
        return start, end
    
    # This month
    if "this month" in query_lower or "current month" in query_lower:
        start = datetime(today.year, today.month, 1).date()
        end = today
        return start, end
    
    # Last year
    if "last year" in query_lower or "previous year" in query_lower:
        start = datetime(today.year - 1, 1, 1).date()
        end = datetime(today.year - 1, 12, 31).date()
        return start, end
    
    # This year
    if "this year" in query_lower or "current year" in query_lower:
        start = datetime(today.year, 1, 1).date()
        end = today
        return start, end
    
    # Last N days
    days_match = re.search(r'last (\d+) days?', query_lower)
    if days_match:
        days = int(days_match.group(1))
        start = (today - timedelta(days=days)).date()
        end = today
        return start, end
    
    # Default: last 30 days
    start = (today - timedelta(days=30)).date()
    end = today
    return start, end


def _extract_category(query: str, user_id: int) -> int | None:
    """
    Extract category from query by matching against user's categories.
    """
    query_lower = query.lower()
    
    # Get user's categories
    categories = db.session.query(Category).filter(Category.user_id == user_id).all()
    
    for cat in categories:
        if cat.name.lower() in query_lower:
            return cat.id
    
    # Common category keywords
    category_keywords = {
        'food': ['food', 'restaurant', 'dining', 'meal', 'lunch', 'dinner', 'breakfast'],
        'transport': ['transport', 'uber', 'taxi', 'gas', 'fuel', 'car'],
        'entertainment': ['entertainment', 'movie', 'game', 'fun'],
        'shopping': ['shopping', 'clothes', 'clothing'],
        'utilities': ['utilities', 'electricity', 'water', 'internet'],
        'health': ['health', 'medical', 'doctor', 'medicine'],
    }
    
    for cat_name, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in query_lower:
                # Try to find matching category
                cat = db.session.query(Category).filter(
                    Category.user_id == user_id,
                    func.lower(Category.name).like(f'%{cat_name}%')
                ).first()
                if cat:
                    return cat.id
    
    return None


def _query_expenses(user_id: int, start_date, end_date, category_id: int | None = None) -> List[Dict]:
    """
    Query expenses with filters.
    """
    query = db.session.query(Expense).filter(
        Expense.user_id == user_id,
        Expense.spent_at >= start_date,
        Expense.spent_at <= end_date,
        Expense.expense_type != "INCOME"
    )
    
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    
    expenses = query.all()
    
    return [{
        'id': e.id,
        'amount': float(e.amount),
        'currency': e.currency,
        'category_id': e.category_id,
        'notes': e.notes,
        'spent_at': e.spent_at.isoformat(),
    } for e in expenses]


def _use_gemini_to_parse(query: str, api_key: str, model: str) -> Dict[str, Any]:
    """
    Use Gemini to parse natural language query into structured format.
    """
    prompt = f"""Parse this financial query into JSON with these keys:
- intent: "spending_query" or "income_query" or "budget_query"
- time_period: "last_quarter", "this_month", "last_year", etc.
- category: extracted category name or null
- amount_comparison: "greater_than", "less_than", "equal_to", or null
- amount_value: numeric value or null

Query: "{query}"

Return ONLY valid JSON, no markdown."""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }).encode("utf-8")
    
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
    
    # Extract JSON from response
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    
    return {}


def process_natural_language_query(user_id: int, query: str) -> Dict[str, Any]:
    """
    Main function to process natural language financial queries.
    
    Args:
        user_id: User ID
        query: Natural language query (e.g., "How much did I spend on food last quarter?")
    
    Returns:
        Dict with answer, source_data, and metadata
    """
    # Parse date range
    start_date, end_date = _parse_date_range(query)
    
    # Extract category
    category_id = _extract_category(query, user_id)
    
    # Get category name if exists
    category_name = None
    if category_id:
        cat = db.session.query(Category).filter(Category.id == category_id).first()
        if cat:
            category_name = cat.name
    
    # Query expenses
    expenses = _query_expenses(user_id, start_date, end_date, category_id)
    
    # Calculate total
    total_amount = sum(e['amount'] for e in expenses)
    
    # Build answer
    period_str = f"{start_date.isoformat()} to {end_date.isoformat()}"
    category_str = f" on {category_name}" if category_name else ""
    
    answer = f"You spent {total_amount:.2f} {expenses[0]['currency'] if expenses else 'INR'}{category_str} from {period_str}."
    
    # Try to use Gemini for better answer formatting if available
    gemini_key = (_settings.gemini_api_key or "").strip()
    if gemini_key and expenses:
        try:
            # Generate natural answer using Gemini
            summary_prompt = f"""Given this financial data, provide a concise, friendly answer to the user's question.

Question: {query}
Total spent: {total_amount:.2f}
Period: {period_str}
Category: {category_name or 'all categories'}
Number of transactions: {len(expenses)}

Provide a 1-2 sentence natural answer."""
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{_settings.gemini_model}:generateContent?key={gemini_key}"
            body = json.dumps({
                "contents": [{"parts": [{"text": summary_prompt}]}],
                "generationConfig": {"temperature": 0.3},
            }).encode("utf-8")
            
            req = request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with request.urlopen(req, timeout=10) as resp:  # nosec B310
                payload = json.loads(resp.read().decode("utf-8"))
            
            ai_answer = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if ai_answer:
                answer = ai_answer
        except Exception:
            pass  # Fall back to default answer
    
    return {
        "answer": answer,
        "total_amount": round(total_amount, 2),
        "currency": expenses[0]['currency'] if expenses else 'INR',
        "transaction_count": len(expenses),
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "category": category_name,
        "source_data": expenses[:10],  # Return max 10 transactions as examples
        "query": query,
    }
