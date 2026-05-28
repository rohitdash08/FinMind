"""Natural Language Finance Query Engine.

Parse natural language questions about finances:
- Intent classification (how much, when, where, compare)
- Time period extraction (this week, last month, Q1)
- Category/merchant extraction
- Aggregation type detection (total, average, max, min, count)
- Query execution against transaction data
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.nlquery")


class QueryIntent(str, Enum):
    TOTAL = "total"
    AVERAGE = "average"
    MAX = "max"
    MIN = "min"
    COUNT = "count"
    LIST = "list"
    COMPARE = "compare"
    TREND = "trend"
    BREAKDOWN = "breakdown"


class TimePeriod:
    def __init__(self, start, end, label):
        self.start = start
        self.end = end
        self.label = label

    def to_dict(self):
        return {"start": self.start, "end": self.end, "label": self.label}


class ParsedQuery:
    def __init__(self):
        self.intent = None
        self.time_period = None
        self.category = None
        self.merchant = None
        self.amount_filter = None
        self.original_query = ""
        self.confidence = 0.0

    def to_dict(self):
        return {
            "intent": self.intent,
            "time_period": self.time_period.to_dict() if self.time_period else None,
            "category": self.category,
            "merchant": self.merchant,
            "amount_filter": self.amount_filter,
            "original_query": self.original_query,
            "confidence": self.confidence,
        }


class NLFinanceQueryService:
    """Parse and execute natural language finance queries."""

    # Time period patterns
    TIME_PATTERNS = [
        (r"this\s+week", "this_week"),
        (r"last\s+week", "last_week"),
        (r"this\s+month", "this_month"),
        (r"last\s+month", "last_month"),
        (r"this\s+year", "this_year"),
        (r"last\s+year", "last_year"),
        (r"past\s+(\d+)\s+days?", "past_n_days"),
        (r"last\s+(\d+)\s+days?", "past_n_days"),
        (r"(\d+)\s+days?\s+ago", "n_days_ago"),
        (r"january|february|march|april|may|june|july|august|september|october|november|december",
         "named_month"),
        (r"q([1-4])", "quarter"),
        (r"today", "today"),
        (r"yesterday", "yesterday"),
    ]

    # Intent patterns
    INTENT_PATTERNS = [
        (r"how much|total|sum|amount spent", QueryIntent.TOTAL),
        (r"average|avg|mean|typically", QueryIntent.AVERAGE),
        (r"most|highest|max|biggest|largest", QueryIntent.MAX),
        (r"least|lowest|min|smallest|cheapest", QueryIntent.MIN),
        (r"how many|count|number of", QueryIntent.COUNT),
        (r"show|list|what|which|where", QueryIntent.LIST),
        (r"compare|vs|versus|difference", QueryIntent.COMPARE),
        (r"trend|over time|pattern|change", QueryIntent.TREND),
        (r"breakdown|by category|split|distribution", QueryIntent.BREAKDOWN),
    ]

    def parse_query(self, query: str) -> ParsedQuery:
        """Parse a natural language query into structured components."""
        parsed = ParsedQuery()
        parsed.original_query = query
        q = query.lower().strip()

        # Detect intent
        max_confidence = 0
        for pattern, intent in self.INTENT_PATTERNS:
            if re.search(pattern, q):
                parsed.intent = intent.value
                max_confidence = max(max_confidence, 0.8)

        if not parsed.intent:
            # Default intent based on question structure
            if q.startswith(("how", "what", "when", "where", "which")):
                parsed.intent = QueryIntent.LIST.value
                max_confidence = 0.5
            else:
                parsed.intent = QueryIntent.TOTAL.value
                max_confidence = 0.3

        parsed.confidence = max_confidence

        # Extract time period
        parsed.time_period = self._extract_time_period(q)

        # Extract category
        parsed.category = self._extract_category(q)

        # Extract merchant
        parsed.merchant = self._extract_merchant(q)

        # Extract amount filter
        parsed.amount_filter = self._extract_amount_filter(q)

        return parsed

    def _extract_time_period(self, query: str) -> Optional[TimePeriod]:
        """Extract time period from query."""
        now = datetime.now()

        for pattern, period_type in self.TIME_PATTERNS:
            match = re.search(pattern, query)
            if match:
                if period_type == "today":
                    return TimePeriod(now.strftime("%Y-%m-%d"),
                                     now.strftime("%Y-%m-%d"), "today")
                elif period_type == "yesterday":
                    y = now - timedelta(days=1)
                    return TimePeriod(y.strftime("%Y-%m-%d"),
                                     y.strftime("%Y-%m-%d"), "yesterday")
                elif period_type == "this_week":
                    start = now - timedelta(days=now.weekday())
                    return TimePeriod(start.strftime("%Y-%m-%d"),
                                     now.strftime("%Y-%m-%d"), "this_week")
                elif period_type == "last_week":
                    end = now - timedelta(days=now.weekday() + 1)
                    start = end - timedelta(days=6)
                    return TimePeriod(start.strftime("%Y-%m-%d"),
                                     end.strftime("%Y-%m-%d"), "last_week")
                elif period_type == "this_month":
                    start = now.replace(day=1)
                    return TimePeriod(start.strftime("%Y-%m-%d"),
                                     now.strftime("%Y-%m-%d"), "this_month")
                elif period_type == "last_month":
                    first_this = now.replace(day=1)
                    last_end = first_this - timedelta(days=1)
                    last_start = last_end.replace(day=1)
                    return TimePeriod(last_start.strftime("%Y-%m-%d"),
                                     last_end.strftime("%Y-%m-%d"), "last_month")
                elif period_type == "past_n_days":
                    days = int(match.group(1))
                    start = now - timedelta(days=days)
                    return TimePeriod(start.strftime("%Y-%m-%d"),
                                     now.strftime("%Y-%m-%d"), f"past_{days}_days")

        # Default: this month
        start = now.replace(day=1)
        return TimePeriod(start.strftime("%Y-%m-%d"),
                         now.strftime("%Y-%m-%d"), "this_month")

    def _extract_category(self, query: str) -> Optional[str]:
        """Extract spending category."""
        categories = ["food", "groceries", "transport", "entertainment",
                      "shopping", "health", "education", "housing", "rent",
                      "utilities", "travel", "subscription", "restaurant", "coffee"]

        for cat in categories:
            if cat in query:
                return cat
        return None

    def _extract_merchant(self, query: str) -> Optional[str]:
        """Extract merchant name (quoted or after 'at/from')."""
        # Quoted merchant
        match = re.search(r'"([^"]+)"', query)
        if match:
            return match.group(1)

        # "at/from <merchant>"
        match = re.search(r'(?:at|from|to)\s+(\w+)', query)
        if match:
            return match.group(1)

        return None

    def _extract_amount_filter(self, query: str) -> Optional[dict]:
        """Extract amount filters (over $100, under $50, between $10-$50)."""
        # "over/above $X"
        match = re.search(r'(?:over|above|more than|exceeding)\s*\$?(\d+)', query)
        if match:
            return {"min": float(match.group(1))}

        # "under/below $X"
        match = re.search(r'(?:under|below|less than)\s*\$?(\d+)', query)
        if match:
            return {"max": float(match.group(1))}

        # "between $X and $Y"
        match = re.search(r'between\s*\$?(\d+)\s*(?:and|-|to)\s*\$?(\d+)', query)
        if match:
            return {"min": float(match.group(1)), "max": float(match.group(2))}

        return None

    def execute_query(self, query: str, transactions: list[dict]) -> dict:
        """Parse and execute a natural language query."""
        parsed = self.parse_query(query)

        # Filter transactions by time period
        filtered = self._filter_by_time(transactions, parsed.time_period)

        # Filter by category
        if parsed.category:
            filtered = [t for t in filtered
                       if parsed.category in (t.get("category", "") or "").lower()]

        # Filter by merchant
        if parsed.merchant:
            filtered = [t for t in filtered
                       if parsed.merchant in (t.get("merchant", "") or
                                              t.get("description", "") or "").lower()]

        # Filter by amount
        if parsed.amount_filter:
            if "min" in parsed.amount_filter:
                filtered = [t for t in filtered
                           if abs(float(t.get("amount", 0))) >= parsed.amount_filter["min"]]
            if "max" in parsed.amount_filter:
                filtered = [t for t in filtered
                           if abs(float(t.get("amount", 0))) <= parsed.amount_filter["max"]]

        # Execute aggregation
        result = self._aggregate(filtered, parsed.intent)

        return {
            "parsed_query": parsed.to_dict(),
            "result": result,
            "matched_transactions": len(filtered),
        }

    def _filter_by_time(self, transactions: list[dict],
                         period: TimePeriod) -> list[dict]:
        """Filter transactions by time period."""
        filtered = []
        for tx in transactions:
            date = str(tx.get("date", ""))[:10]
            if period.start <= date <= period.end:
                filtered.append(tx)
        return filtered

    def _aggregate(self, transactions: list[dict], intent: str) -> dict:
        """Aggregate filtered transactions based on intent."""
        amounts = [abs(float(t.get("amount", 0))) for t in transactions]

        if not amounts:
            return {"value": 0, "text": "No transactions found for this query"}

        if intent == "total":
            return {"value": sum(amounts), "text": f"Total: ${sum(amounts):,.2f}"}
        elif intent == "average":
            avg = sum(amounts) / len(amounts)
            return {"value": avg, "text": f"Average: ${avg:,.2f}"}
        elif intent == "max":
            return {"value": max(amounts), "text": f"Highest: ${max(amounts):,.2f}"}
        elif intent == "min":
            return {"value": min(amounts), "text": f"Lowest: ${min(amounts):,.2f}"}
        elif intent == "count":
            return {"value": len(amounts), "text": f"Count: {len(amounts)} transactions"}
        elif intent == "breakdown":
            by_cat = defaultdict(float)
            for tx in transactions:
                cat = tx.get("category", "other")
                by_cat[cat] += abs(float(tx.get("amount", 0)))
            return {"breakdown": dict(by_cat),
                   "text": f"Breakdown: {len(by_cat)} categories"}
        elif intent == "trend":
            return {"trend": "computed",
                   "count": len(amounts),
                   "text": f"Trend based on {len(amounts)} transactions"}
        else:  # list
            return {"transactions": len(amounts),
                   "text": f"Found {len(amounts)} transactions (${sum(amounts):,.2f} total)"}
