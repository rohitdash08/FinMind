"""Credit Score Tracker & Simulator.

Features:
- Credit score tracking over time
- Score simulator (what-if scenarios)
- Factor breakdown
- Improvement suggestions
- Credit utilization calculator
- Score history and trends
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.credit")


class CreditFactor:
    PAYMENT_HISTORY = "payment_history"       # 35%
    CREDIT_UTILIZATION = "credit_utilization"  # 30%
    CREDIT_AGE = "credit_age"                  # 15%
    CREDIT_MIX = "credit_mix"                  # 10%
    NEW_CREDIT = "new_credit"                  # 10%

    WEIGHTS = {
        "payment_history": 0.35,
        "credit_utilization": 0.30,
        "credit_age": 0.15,
        "credit_mix": 0.10,
        "new_credit": 0.10,
    }


class CreditScoreService:

    def __init__(self):
        self.scores = {}  # user_id -> list of score records
        self.accounts = defaultdict(list)

    def add_score(self, user_id: str, score: int, source: str = "manual",
                   date: str = None) -> dict:
        """Record a credit score."""
        if not 300 <= score <= 850:
            return {"error": "Score must be between 300-850"}

        record = {
            "score_id": str(uuid4())[:8],
            "score": score,
            "source": source,
            "date": date or datetime.utcnow().isoformat()[:10],
            "rating": self._score_rating(score),
        }

        if user_id not in self.scores:
            self.scores[user_id] = []
        self.scores[user_id].append(record)
        self.scores[user_id].sort(key=lambda x: x["date"])

        return {
            "status": "recorded",
            **record,
            "trend": self._get_trend(user_id),
        }

    def get_history(self, user_id: str, limit: int = 12) -> dict:
        """Get score history."""
        records = self.scores.get(user_id, [])

        if not records:
            return {"scores": [], "current": None, "change": 0}

        latest = records[-1]
        change = 0
        if len(records) >= 2:
            change = latest["score"] - records[-2]["score"]

        # Score range over time
        scores = [r["score"] for r in records]
        return {
            "scores": records[-limit:],
            "current": latest,
            "change": change,
            "change_direction": "up" if change > 0 else "down" if change < 0 else "stable",
            "highest": max(scores),
            "lowest": min(scores),
            "average": round(sum(scores) / len(scores), 0),
        }

    def simulate(self, user_id: str, current_score: int,
                  actions: list[str]) -> dict:
        """Simulate score changes from actions."""
        if not 300 <= current_score <= 850:
            return {"error": "Invalid score"}

        factors = self._estimate_factors(current_score)
        changes = {}
        total_change = 0

        action_impacts = {
            "pay_all_on_time": {"factor": "payment_history", "points": 15, "months": 1},
            "miss_payment": {"factor": "payment_history", "points": -60, "months": 1},
            "reduce_utilization_50": {"factor": "credit_utilization", "points": 10, "months": 1},
            "reduce_utilization_10": {"factor": "credit_utilization", "points": 25, "months": 2},
            "max_out_cards": {"factor": "credit_utilization", "points": -40, "months": 1},
            "open_new_card": {"factor": "new_credit", "points": -5, "months": 1},
            "close_old_card": {"factor": "credit_age", "points": -15, "months": 2},
            "add_credit_mix": {"factor": "credit_mix", "points": 10, "months": 3},
            "pay_collections": {"factor": "payment_history", "points": 20, "months": 2},
            "dispute_error": {"factor": "payment_history", "points": 30, "months": 1},
            "become_authorized_user": {"factor": "credit_age", "points": 15, "months": 2},
        }

        for action in actions:
            if action in action_impacts:
                impact = action_impacts[action]
                changes[action] = {
                    "factor": impact["factor"],
                    "points": impact["points"],
                    "months_to_impact": impact["months"],
                    "description": action.replace("_", " ").title(),
                }
                total_change += impact["points"]

        new_score = max(300, min(850, current_score + total_change))

        return {
            "current_score": current_score,
            "simulated_score": new_score,
            "total_change": total_change,
            "actions": changes,
            "new_rating": self._score_rating(new_score),
        }

    def get_factor_breakdown(self, user_id: str,
                               score: int = None) -> dict:
        """Break down score factors."""
        if score is None:
            records = self.scores.get(user_id, [])
            if records:
                score = records[-1]["score"]
            else:
                score = 700

        factors = self._estimate_factors(score)

        breakdown = []
        for factor, weight in CreditFactor.WEIGHTS.items():
            data = factors[factor]
            breakdown.append({
                "factor": factor,
                "weight": f"{int(weight * 100)}%",
                "status": data["status"],
                "description": data["description"],
                "score_contribution": round(score * weight * data["multiplier"]),
            })

        return {
            "score": score,
            "rating": self._score_rating(score),
            "factors": breakdown,
        }

    def get_improvement_plan(self, user_id: str,
                               current_score: int = None,
                               target_score: int = 750) -> dict:
        """Generate improvement plan."""
        if current_score is None:
            records = self.scores.get(user_id, [])
            current_score = records[-1]["score"] if records else 680

        gap = target_score - current_score
        if gap <= 0:
            return {
                "current_score": current_score,
                "target_score": target_score,
                "gap": 0,
                "status": "target_reached",
                "actions": [],
            }

        actions = []

        if gap >= 30:
            actions.append({
                "priority": 1,
                "action": "Ensure all payments are on time",
                "impact": "+15-25 points",
                "timeline": "1-2 months",
                "difficulty": "easy",
            })

        if gap >= 20:
            actions.append({
                "priority": 2,
                "action": "Reduce credit utilization below 10%",
                "impact": "+10-25 points",
                "timeline": "1-2 months",
                "difficulty": "medium",
            })

        if gap >= 40:
            actions.append({
                "priority": 3,
                "action": "Dispute any errors on credit report",
                "impact": "+10-30 points",
                "timeline": "1-3 months",
                "difficulty": "medium",
            })

        if gap >= 50:
            actions.append({
                "priority": 4,
                "action": "Pay off collections accounts",
                "impact": "+15-20 points",
                "timeline": "1-2 months",
                "difficulty": "medium",
            })

        if gap >= 25:
            actions.append({
                "priority": 5,
                "action": "Become authorized user on old account",
                "impact": "+10-15 points",
                "timeline": "1-2 months",
                "difficulty": "easy",
            })

        if gap >= 15:
            actions.append({
                "priority": 6,
                "action": "Diversify credit mix (installment + revolving)",
                "impact": "+5-10 points",
                "timeline": "3-6 months",
                "difficulty": "hard",
            })

        actions.append({
            "priority": 7,
            "action": "Keep old accounts open",
            "impact": "+5-15 points",
            "timeline": "Ongoing",
            "difficulty": "easy",
        })

        return {
            "current_score": current_score,
            "target_score": target_score,
            "gap": gap,
            "estimated_months": min(max(gap // 10, 1), 24),
            "actions": sorted(actions, key=lambda x: x["priority"]),
        }

    def calculate_utilization(self, balances: list[float],
                                limits: list[float]) -> dict:
        """Calculate credit utilization."""
        total_balance = sum(balances)
        total_limit = sum(limits)
        overall_rate = total_balance / max(total_limit, 1) * 100

        cards = []
        for i, (bal, lim) in enumerate(zip(balances, limits)):
            rate = bal / max(lim, 1) * 100
            cards.append({
                "card": f"Card {i+1}",
                "balance": round(bal, 2),
                "limit": round(lim, 2),
                "utilization": round(rate, 1),
                "status": "good" if rate < 30 else "warning" if rate < 50 else "danger",
            })

        return {
            "total_balance": round(total_balance, 2),
            "total_limit": round(total_limit, 2),
            "overall_utilization": round(overall_rate, 1),
            "status": "excellent" if overall_rate < 10 else
                     "good" if overall_rate < 30 else
                     "fair" if overall_rate < 50 else "poor",
            "recommended_paydown": round(max(total_balance - total_limit * 0.1, 0), 2),
            "cards": cards,
        }

    def _score_rating(self, score: int) -> str:
        if score >= 800: return "exceptional"
        if score >= 740: return "very_good"
        if score >= 670: return "good"
        if score >= 580: return "fair"
        return "poor"

    def _get_trend(self, user_id: str) -> str:
        records = self.scores.get(user_id, [])
        if len(records) < 2:
            return "new"
        return "improving" if records[-1]["score"] > records[-2]["score"] else                "declining" if records[-1]["score"] < records[-2]["score"] else "stable"

    def _estimate_factors(self, score: int) -> dict:
        """Estimate factor contributions based on score."""
        if score >= 750:
            return {
                "payment_history": {"status": "excellent", "multiplier": 1.0,
                    "description": "No missed payments"},
                "credit_utilization": {"status": "excellent", "multiplier": 1.0,
                    "description": "Below 10% utilization"},
                "credit_age": {"status": "good", "multiplier": 0.9,
                    "description": "Average age 7+ years"},
                "credit_mix": {"status": "good", "multiplier": 0.85,
                    "description": "Diverse credit types"},
                "new_credit": {"status": "good", "multiplier": 0.9,
                    "description": "Few recent inquiries"},
            }
        elif score >= 650:
            return {
                "payment_history": {"status": "good", "multiplier": 0.85,
                    "description": "1-2 late payments"},
                "credit_utilization": {"status": "fair", "multiplier": 0.7,
                    "description": "30-50% utilization"},
                "credit_age": {"status": "fair", "multiplier": 0.7,
                    "description": "Average age 3-7 years"},
                "credit_mix": {"status": "fair", "multiplier": 0.7,
                    "description": "Limited credit types"},
                "new_credit": {"status": "fair", "multiplier": 0.75,
                    "description": "Some recent inquiries"},
            }
        else:
            return {
                "payment_history": {"status": "poor", "multiplier": 0.5,
                    "description": "Multiple missed payments"},
                "credit_utilization": {"status": "poor", "multiplier": 0.5,
                    "description": "Over 50% utilization"},
                "credit_age": {"status": "poor", "multiplier": 0.5,
                    "description": "Short credit history"},
                "credit_mix": {"status": "poor", "multiplier": 0.5,
                    "description": "No credit diversity"},
                "new_credit": {"status": "poor", "multiplier": 0.5,
                    "description": "Many recent inquiries"},
            }
