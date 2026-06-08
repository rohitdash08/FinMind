from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from ..extensions import db
from ..models import Expense

bp = Blueprint("subscriptions", __name__)
logger = logging.getLogger("finmind.subscriptions")

SUBSCRIPTION_KEYWORDS = {
    "netflix", "spotify", "hulu", "aws", "digitalocean", "github", 
    "adobe", "prime", "apple", "google", "microsoft", "gym", "cloud",
    "subscription", "membership"
}

@bp.get("/detected")
@jwt_required()
def detect_subscriptions():
    uid = int(get_jwt_identity())
    
    try:
        months = int(request.args.get("months", 6))
    except ValueError:
        months = 6
        
    cutoff_date = date.today() - timedelta(days=30 * months)
    
    # Fetch expenses
    expenses = db.session.query(Expense).filter(
        Expense.user_id == uid,
        Expense.expense_type != 'INCOME',
        Expense.spent_at >= cutoff_date,
        Expense.notes != None
    ).order_by(Expense.spent_at.asc()).all()
    
    merchants = {}
    for exp in expenses:
        merchant = exp.notes.lower().strip()
        if not merchant:
            continue
        if merchant not in merchants:
            merchants[merchant] = []
        merchants[merchant].append(exp)
        
    subscriptions = []
    
    for merchant, exps in merchants.items():
        if len(exps) < 2:
            continue
            
        amounts = [float(e.amount) for e in exps]
        avg_amount = sum(amounts) / len(amounts)
        
        intervals = []
        for i in range(1, len(exps)):
            intervals.append((exps[i].spent_at - exps[i-1].spent_at).days)
            
        avg_interval = sum(intervals) / len(intervals)
        
        cadence = "unknown"
        monthly_estimate = avg_amount
        
        if 25 <= avg_interval <= 35:
            cadence = "monthly"
            monthly_estimate = avg_amount
        elif 5 <= avg_interval <= 9:
            cadence = "weekly"
            monthly_estimate = avg_amount * 4.33
        elif 350 <= avg_interval <= 380:
            cadence = "yearly"
            monthly_estimate = avg_amount / 12
            
        keyword_match = any(kw in merchant for kw in SUBSCRIPTION_KEYWORDS)
        
        confidence = "low"
        if cadence != "unknown" and keyword_match:
            confidence = "high"
        elif cadence != "unknown":
            confidence = "medium"
        elif keyword_match:
            confidence = "low"
        else:
            # If no keyword and irregular cadence, skip
            continue
            
        subscriptions.append({
            "merchant": merchant,
            "cadence": cadence,
            "occurrences": len(exps),
            "average_amount": round(avg_amount, 2),
            "currency": exps[-1].currency,
            "monthly_estimate": round(monthly_estimate, 2),
            "confidence": confidence,
            "keyword_match": keyword_match,
            "first_charge": exps[0].spent_at.isoformat(),
            "last_charge": exps[-1].spent_at.isoformat(),
        })
        
    subscriptions.sort(key=lambda s: s["monthly_estimate"], reverse=True)
    total_monthly_estimate = round(sum(s["monthly_estimate"] for s in subscriptions), 2)
    
    return jsonify({
        "subscriptions": subscriptions,
        "total_monthly_estimate": total_monthly_estimate,
        "analysis_period_months": months
    }), 200
