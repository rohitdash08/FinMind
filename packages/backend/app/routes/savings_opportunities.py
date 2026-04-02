from datetime import date, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, extract, desc
from collections import defaultdict
import logging
from ..extensions import db
from ..models import Expense, Category
from ..services.cache import cache_get, cache_set

bp = Blueprint('savings_opportunities', __name__)
logger = logging.getLogger('finmind.savings_opportunities')


def _savings_cache_key(user_id: int, months: int) -> str:
    return f'user:{user_id}:savings_opportunities:{months}'


@bp.get('')
@jwt_required()
def get_savings_opportunities():
    """Analyze spending patterns and identify savings opportunities."""
    uid = int(get_jwt_identity())
    
    try:
        months = min(12, max(1, int(request.args.get('months', 6))))
        min_confidence = min(100, max(0, int(request.args.get('min_confidence', 50))))
    except ValueError:
        return jsonify(error='invalid parameters'), 400
    
    cache_key = _savings_cache_key(uid, months)
    cached = cache_get(cache_key)
    if cached:
        logger.info('Savings opportunities cache hit user=%s', uid)
        return jsonify(cached)
    
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=months * 30)
        
        expenses = (
            db.session.query(Expense)
            .filter(
                Expense.user_id == uid,
                Expense.spent_at >= start_date,
                Expense.spent_at <= end_date,
                Expense.expense_type != 'INCOME',
            )
            .all()
        )
        
        if not expenses:
            return jsonify({
                'opportunities': [],
                'summary': {
                    'total_analyzed': 0,
                    'potential_savings': 0,
                    'analysis_period_months': months,
                },
            })
        
        opportunities = []
        
        category_opportunities = _analyze_category_trends(uid, expenses, months)
        opportunities.extend(category_opportunities)
        
        frequency_opportunities = _analyze_high_frequency_expenses(uid, expenses, months)
        opportunities.extend(frequency_opportunities)
        
        recurring_opportunities = _detect_potential_subscriptions(uid, expenses, months)
        opportunities.extend(recurring_opportunities)
        
        spike_opportunities = _detect_spending_spikes(uid, expenses, months)
        opportunities.extend(spike_opportunities)
        
        opportunities = [o for o in opportunities if o['confidence'] >= min_confidence]
        opportunities.sort(key=lambda x: x['potential_savings'], reverse=True)
        
        total_potential = sum(o['potential_savings'] for o in opportunities)
        
        response = {
            'opportunities': opportunities,
            'summary': {
                'total_analyzed': len(expenses),
                'potential_savings': round(total_potential, 2),
                'analysis_period_months': months,
                'categories_analyzed': len(set(e.category_id for e in expenses if e.category_id)),
            },
            'generated_at': date.today().isoformat(),
        }
        
        cache_set(cache_key, response, ttl_seconds=3600)
        
        logger.info(
            'Savings opportunities generated user=%s opportunities=%d potential_savings=%.2f',
            uid, len(opportunities), total_potential,
        )
        
        return jsonify(response)
    
    except Exception as e:
        logger.exception('Savings opportunities failed user=%s', uid)
        return jsonify(error='failed to analyze savings opportunities', details=str(e)), 500


def _analyze_category_trends(uid: int, expenses: list, months: int) -> list:
    """Identify categories with increasing spending trends."""
    opportunities = []
    category_monthly = defaultdict(lambda: defaultdict(Decimal))
    category_names = {}
    
    for exp in expenses:
        if exp.category_id:
            month_key = exp.spent_at.strftime('%Y-%m')
            category_monthly[exp.category_id][month_key] += exp.amount
    
    if category_monthly:
        cat_ids = list(category_monthly.keys())
        cats = db.session.query(Category).filter(Category.id.in_(cat_ids)).all()
        category_names = {c.id: c.name for c in cats}
    
    for cat_id, monthly_data in category_monthly.items():
        months_list = sorted(monthly_data.keys())
        if len(months_list) < 2:
            continue
        
        values = [float(monthly_data[m]) for m in months_list]
        n = len(values)
        if n < 2:
            continue
        
        changes = []
        for i in range(1, n):
            if values[i-1] > 0:
                change_pct = ((values[i] - values[i-1]) / values[i-1]) * 100
                changes.append(change_pct)
        
        if not changes:
            continue
        
        avg_change = sum(changes) / len(changes)
        recent_total = sum(values[-2:])
        older_total = sum(values[:-2]) if len(values) > 2 else values[0]
        
        if avg_change > 10 and len([c for c in changes if c > 0]) >= len(changes) * 0.6:
            if older_total > 0:
                potential_savings = recent_total - older_total
                if potential_savings > 0:
                    confidence = min(95, 50 + int(avg_change))
                    opportunities.append({
                        'type': 'increasing_trend',
                        'category': category_names.get(cat_id, f'Category {cat_id}'),
                        'category_id': cat_id,
                        'description': f'Spending in {category_names.get(cat_id, "this category")} has increased by {avg_change:.1f}% per month on average',
                        'potential_savings': round(potential_savings / 2, 2),
                        'confidence': confidence,
                        'details': {
                            'average_monthly_increase_pct': round(avg_change, 2),
                            'recent_2_months_total': round(recent_total, 2),
                            'previous_period_total': round(older_total, 2),
                            'trend_months': n,
                        },
                    })
    
    return opportunities


def _analyze_high_frequency_expenses(uid: int, expenses: list, months: int) -> list:
    """Identify high-frequency small expenses that add up."""
    opportunities = []
    expense_freq = defaultdict(list)
    
    for exp in expenses:
        if exp.notes:
            normalized = exp.notes.lower().strip()
            expense_freq[normalized].append(exp)
    
    for description, exp_list in expense_freq.items():
        if len(exp_list) >= 4:
            total = sum(float(e.amount) for e in exp_list)
            avg_amount = total / len(exp_list)
            
            if len(exp_list) >= months:
                frequency = 'high'
                confidence = 85
            elif len(exp_list) >= months / 2:
                frequency = 'moderate'
                confidence = 70
            else:
                continue
            
            annual_impact = total * (12 / months)
            
            if annual_impact > 100:
                opportunities.append({
                    'type': 'high_frequency',
                    'category': 'Frequent Expense',
                    'description': f'Frequent expense "{description[:50]}" occurs {len(exp_list)} times - consider if all are necessary',
                    'potential_savings': round(annual_impact * 0.3, 2),
                    'confidence': confidence,
                    'details': {
                        'frequency': frequency,
                        'occurrences': len(exp_list),
                        'total_spent': round(total, 2),
                        'average_amount': round(avg_amount, 2),
                        'estimated_annual_impact': round(annual_impact, 2),
                        'sample_descriptions': [e.notes for e in exp_list[:3]],
                    },
                })
    
    return opportunities


def _detect_potential_subscriptions(uid: int, expenses: list, months: int) -> list:
    """Detect recurring charges that might be subscriptions."""
    opportunities = []
    subscription_candidates = defaultdict(list)
    
    for exp in expenses:
        rounded_amount = round(float(exp.amount) / 5) * 5
        key = (rounded_amount, (exp.notes or '')[:20].lower())
        subscription_candidates[key].append(exp)
    
    for (amount, desc_prefix), exp_list in subscription_candidates.items():
        if len(exp_list) >= 2 and len(exp_list) <= months + 1:
            dates = sorted([e.spent_at for e in exp_list])
            intervals = []
            for i in range(1, len(dates)):
                interval = (dates[i] - dates[i-1]).days
                intervals.append(interval)
            
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                if 25 <= avg_interval <= 38:
                    total = sum(float(e.amount) for e in exp_list)
                    annual_cost = (total / len(exp_list)) * 12
                    
                    opportunities.append({
                        'type': 'potential_subscription',
                        'category': 'Subscription',
                        'description': f'Potential subscription detected: "{exp_list[0].notes[:50]}" - review if still needed',
                        'potential_savings': round(annual_cost / 12, 2),
                        'confidence': 75,
                        'details': {
                            'average_amount': round(amount, 2),
                            'occurrences': len(exp_list),
                            'average_interval_days': round(avg_interval, 1),
                            'estimated_annual_cost': round(annual_cost, 2),
                            'recent_dates': [d.isoformat() for d in dates[-3:]],
                        },
                    })
    
    return opportunities


def _detect_spending_spikes(uid: int, expenses: list, months: int) -> list:
    """Identify unusual spending spikes."""
    opportunities = []
    daily_spending = defaultdict(Decimal)
    
    for exp in expenses:
        daily_spending[exp.spent_at] += exp.amount
    
    if len(daily_spending) < 7:
        return opportunities
    
    amounts = [float(v) for v in daily_spending.values()]
    avg_daily = sum(amounts) / len(amounts)
    variance = sum((x - avg_daily) ** 2 for x in amounts) / len(amounts)
    std_dev = variance ** 0.5
    threshold = avg_daily + (2 * std_dev)
    
    spike_days = [(day, float(amount)) for day, amount in daily_spending.items() if float(amount) > threshold]
    
    if spike_days:
        total_spike_amount = sum(amount for _, amount in spike_days)
        excess = sum(amount - avg_daily for _, amount in spike_days)
        
        opportunities.append({
            'type': 'spending_spike',
            'category': 'Unusual Spending',
            'description': f'{len(spike_days)} days with unusually high spending detected - review these for potential savings',
            'potential_savings': round(excess * 0.5, 2),
            'confidence': 60,
            'details': {
                'spike_count': len(spike_days),
                'average_daily': round(avg_daily, 2),
                'spike_threshold': round(threshold, 2),
                'total_spike_amount': round(total_spike_amount, 2),
                'excess_amount': round(excess, 2),
                'spike_dates': [day.isoformat() for day, _ in sorted(spike_days, reverse=True)[:5]],
            },
        })
    
    return opportunities
