"""
Subscription detection service for auto-detecting recurring charges from expenses.
"""

from datetime import date, timedelta, datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import logging
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Subscription, SubscriptionCadence, SubscriptionStatus

logger = logging.getLogger("finmind.subscriptions")


class SubscriptionDetector:
    """Detect subscription patterns from user expenses."""
    
    # Minimum data points for reliable detection
    MIN_OCCURRENCES = 3
    MIN_CONFIDENCE = 0.6
    
    # Date variance thresholds (in days) for pattern matching
    WEEKLY_TOLERANCE = 3      # ±3 days from expected weekly date
    MONTHLY_TOLERANCE = 5     # ±5 days from expected monthly date
    YEARLY_TOLERANCE = 10     # ±10 days from expected yearly date
    
    # Amount variance threshold (percentage)
    AMOUNT_VARIANCE_THRESHOLD = 0.05  # 5%
    
    def detect_subscriptions(self, user_id: int) -> List[Subscription]:
        """
        Analyze user expenses and detect potential subscriptions.
        Returns a list of Subscription objects (not yet persisted).
        """
        # Get all expenses for the user, ordered by date
        expenses = (
            db.session.query(Expense)
            .filter_by(user_id=user_id)
            .order_by(Expense.spent_at, Expense.notes)
            .all()
        )
        
        if len(expenses) < self.MIN_OCCURRENCES:
            return []
        
        # Group expenses by (merchant, currency)
        groups = self._group_by_merchant_and_currency(expenses)
        
        subscriptions = []
        for (merchant_name, currency), expense_list in groups.items():
            if len(expense_list) < self.MIN_OCCURRENCES:
                continue
                
            # Analyze each merchant for recurring patterns
            sub = self._analyze_merchant_pattern(user_id, merchant_name, currency, expense_list)
            if sub and sub.confidence_score >= self.MIN_CONFIDENCE:
                subscriptions.append(sub)
        
        return subscriptions
    
    def _group_by_merchant_and_currency(self, expenses: List[Expense]) -> Dict[Tuple[str, str], List[Expense]]:
        """Group expenses by (normalized merchant name, currency)."""
        groups = defaultdict(list)
        for exp in expenses:
            merchant = self._normalize_merchant_name(exp.notes or "")
            if merchant:
                key = (merchant, exp.currency)
                groups[key].append(exp)
        return groups
    
    def _normalize_merchant_name(self, notes: str) -> str:
        """
        Normalize merchant name from expense notes.
        Simple approach: lowercase, strip, remove common prefixes.
        """
        if not notes:
            return ""
        
        # Basic normalization
        normalized = notes.strip().lower()
        
        # Remove common prefixes that might interfere
        prefixes = ["payment to ", "paid to ", "transaction at ", "purchase at "]
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        
        return normalized if normalized else notes.strip()
    
    def _analyze_merchant_pattern(self, user_id: int, merchant: str, currency: str, expenses: List[Expense]) -> Optional[Subscription]:
        """
        Analyze a group of expenses to determine if they represent a subscription.
        """
        if len(expenses) < self.MIN_OCCURRENCES:
            return None
        
        # Sort by date
        expenses.sort(key=lambda e: e.spent_at)
        
        # Calculate date intervals
        intervals = self._calculate_intervals(expenses)
        if not intervals:
            return None
        
        # Detect cadence
        cadence, avg_interval_days, interval_std = self._detect_cadence(intervals)
        if not cadence:
            return None
        
        # Check amount consistency
        amounts = [float(exp.amount) for exp in expenses]
        avg_amount = sum(amounts) / len(amounts)
        amount_variance = self._calculate_variance(amounts, avg_amount)
        
        # Calculate confidence score
        confidence = self._calculate_confidence(
            len(expenses), avg_interval_days, interval_std, amount_variance, cadence
        )
        
        # Determine tolerance based on cadence
        tolerance = self._get_tolerance_for_cadence(cadence)
        
        # Check if intervals are regular within tolerance
        regularity_score = self._calculate_regularity(intervals, tolerance)
        
        # Adjust confidence based on regularity
        confidence *= regularity_score
        
        if confidence < self.MIN_CONFIDENCE:
            return None
        
        # Calculate average amount and variance as Decimal
        avg_amount_dec = Decimal(str(round(avg_amount, 2)))
        variance_dec = Decimal(str(round(amount_variance, 2)))
        
        # Predict next date
        next_date = self._predict_next_date(expenses[-1].spent_at, cadence)
        
        # Create Subscription object
        subscription = Subscription(
            user_id=user_id,
            merchant_name=merchant.title(),  # Nice formatting
            amount=avg_amount_dec,
            currency=currency,
            detected_cadence=cadence,
            confidence_score=Decimal(str(round(confidence, 2))),
            occurrence_count=len(expenses),
            first_occurrence_date=expenses[0].spent_at,
            last_occurrence_date=expenses[-1].spent_at,
            next_predicted_date=next_date,
            average_amount=avg_amount_dec,
            amount_variance=variance_dec,
            status=SubscriptionStatus.DETECTED,
            notes=f"Auto-detected from {len(expenses)} occurrences"
        )
        
        return subscription
    
    def _calculate_intervals(self, expenses: List[Expense]) -> List[int]:
        """Calculate days between consecutive expenses."""
        intervals = []
        for i in range(1, len(expenses)):
            delta = (expenses[i].spent_at - expenses[i-1].spent_at).days
            intervals.append(delta)
        return intervals
    
    def _detect_cadence(self, intervals: List[int]) -> Tuple[Optional[SubscriptionCadence], float, float]:
        """
        Determine the most likely cadence based on intervals.
        Returns (cadence, average_days, standard_deviation).
        """
        if not intervals:
            return None, 0.0, 0.0
        
        avg_interval = sum(intervals) / len(intervals)
        std_dev = self._std_deviation(intervals, avg_interval)
        
        # Check for weekly pattern (6-8 days, allowing for weekend shifts)
        if 6 <= avg_interval <= 8 and std_dev <= self.WEEKLY_TOLERANCE:
            return SubscriptionCadence.WEEKLY, avg_interval, std_dev
        
        # Check for monthly pattern (25-35 days)
        if 25 <= avg_interval <= 35 and std_dev <= self.MONTHLY_TOLERANCE:
            return SubscriptionCadence.MONTHLY, avg_interval, std_dev
        
        # Check for yearly pattern (350-380 days)
        if 350 <= avg_interval <= 380 and std_dev <= self.YEARLY_TOLERANCE:
            return SubscriptionCadence.YEARLY, avg_interval, std_dev
        
        return None, avg_interval, std_dev
    
    def _calculate_variance(self, values: List[float], mean: float) -> float:
        """Calculate variance as percentage of mean."""
        if len(values) < 2:
            return 0.0
        squared_diffs = [(v - mean) ** 2 for v in values]
        variance = sum(squared_diffs) / len(values)
        # Return as percentage of mean
        return (variance ** 0.5) / mean if mean > 0 else 0.0
    
    def _calculate_confidence(self, count: int, avg_interval: float, std_dev: float, 
                             amount_variance: float, cadence: SubscriptionCadence) -> float:
        """
        Calculate confidence score (0.0-1.0) based on:
        - Number of occurrences
        - Interval regularity
        - Amount consistency
        """
        score = 0.0
        
        # Base score from occurrence count (more data = more confident)
        count_score = min(count / 12.0, 1.0)  # Cap at 12 occurrences
        score += count_score * 0.3
        
        # Interval regularity score
        tolerance = self._get_tolerance_for_cadence(cadence)
        regularity = max(0.0, 1.0 - (std_dev / tolerance))
        score += regularity * 0.4
        
        # Amount consistency score
        amount_consistency = max(0.0, 1.0 - (amount_variance / self.AMOUNT_VARIANCE_THRESHOLD))
        score += amount_consistency * 0.3
        
        return min(score, 1.0)
    
    def _calculate_regularity(self, intervals: List[int], tolerance: int) -> float:
        """
        Calculate how regular the intervals are within tolerance.
        Returns score between 0.0 and 1.0.
        """
        if not intervals:
            return 0.0
        
        # For detected cadences, intervals should already be close
        # This calculates the proportion of intervals within extended tolerance
        extended_tolerance = tolerance * 2
        within_tolerance = sum(1 for i in intervals if abs(i - intervals[0]) <= extended_tolerance)
        return within_tolerance / len(intervals)
    
    def _get_tolerance_for_cadence(self, cadence: SubscriptionCadence) -> int:
        """Get day tolerance for a given cadence."""
        if cadence == SubscriptionCadence.WEEKLY:
            return self.WEEKLY_TOLERANCE
        if cadence == SubscriptionCadence.MONTHLY:
            return self.MONTHLY_TOLERANCE
        if cadence == SubscriptionCadence.YEARLY:
            return self.YEARLY_TOLERANCE
        return 5
    
    def _predict_next_date(self, last_date: date, cadence: SubscriptionCadence) -> date:
        """Predict the next occurrence date based on cadence."""
        if cadence == SubscriptionCadence.WEEKLY:
            return last_date + timedelta(days=7)
        if cadence == SubscriptionCadence.MONTHLY:
            year = last_date.year + (1 if last_date.month == 12 else 0)
            month = 1 if last_date.month == 12 else last_date.month + 1
            day = min(last_date.day, self._days_in_month(year, month))
            return date(year, month, day)
        if cadence == SubscriptionCadence.YEARLY:
            return date(last_date.year + 1, last_date.month, last_date.day)
        return last_date
    
    def _days_in_month(self, year: int, month: int) -> int:
        """Get number of days in a month."""
        import calendar
        return calendar.monthrange(year, month)[1]
    
    def _std_deviation(self, values: List[float], mean: float) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
    
    def refresh_predictions(self, user_id: int) -> None:
        """Update next_predicted_date for all confirmed subscriptions."""
        subscriptions = (
            db.session.query(Subscription)
            .filter_by(user_id=user_id, status=SubscriptionStatus.CONFIRMED)
            .all()
        )
        
        for sub in subscriptions:
            sub.next_predicted_date = self._predict_next_date(
                sub.last_occurrence_date, sub.detected_cadence
            )
        
        db.session.commit()


def detect_and_create_subscriptions(user_id: int) -> List[Subscription]:
    """
    Run detection for a user and persist new subscriptions.
    Returns list of newly created subscriptions.
    """
    detector = SubscriptionDetector()
    detected = detector.detect_subscriptions(user_id)
    
    # Check which ones are new (not already in DB with similar pattern)
    new_subs = []
    for sub in detected:
        # Simple deduplication: check if there's an existing subscription
        # with same user, merchant, and cadence that is CONFIRMED or DETECTED
        existing = (
            db.session.query(Subscription)
            .filter_by(
                user_id=user_id,
                merchant_name=sub.merchant_name,
                detected_cadence=sub.detected_cadence,
            )
            .filter(Subscription.status.in_([SubscriptionStatus.DETECTED, SubscriptionStatus.CONFIRMED]))
            .first()
        )
        
        if not existing:
            db.session.add(sub)
            new_subs.append(sub)
    
    db.session.commit()
    logger.info("Detected %d new subscriptions for user %s", len(new_subs), user_id)
    return new_subs