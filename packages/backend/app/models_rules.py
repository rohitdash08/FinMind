"""Rule-based auto tagging and categorization models for FinMind.

Users define rules like:
- IF merchant contains "starbucks" THEN tag: coffee, category: Food & Drink
- IF amount > 100 AND merchant contains "amazon" THEN tag: shopping, priority: review
"""

from datetime import datetime, timezone
from ..extensions import db


class TaggingRule(db.Model):
    """User-defined rule for auto-tagging transactions."""
    __tablename__ = "tagging_rules"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=0)  # Higher = checked first

    # Conditions (stored as JSON)
    conditions = db.Column(db.JSON, nullable=False)
    # Examples:
    # {"field": "merchant", "operator": "contains", "value": "starbucks"}
    # {"field": "amount", "operator": "greater_than", "value": 100}
    # {"logic": "AND", "rules": [...]}

    # Actions
    tag = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    note = db.Column(db.String(500), nullable=True)

    # Stats
    match_count = db.Column(db.Integer, default=0)
    last_matched = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    FIELDS = ["merchant", "description", "amount", "category", "note"]
    OPERATORS = [
        "contains", "not_contains", "equals", "not_equals",
        "starts_with", "ends_with", "regex",
        "greater_than", "less_than", "between",
    ]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "is_active": self.is_active,
            "priority": self.priority,
            "conditions": self.conditions,
            "tag": self.tag,
            "category": self.category,
            "note": self.note,
            "match_count": self.match_count,
            "last_matched": self.last_matched.isoformat() if self.last_matched else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
