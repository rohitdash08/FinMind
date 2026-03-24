from datetime import datetime, date
from enum import Enum
from sqlalchemy import Enum as SAEnum
from .extensions import db


class Role(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    preferred_currency = db.Column(db.String(10), default="INR", nullable=False)
    role = db.Column(db.String(20), default=Role.USER.value, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    expense_type = db.Column(db.String(20), default="EXPENSE", nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    spent_at = db.Column(db.Date, default=date.today, nullable=False)
    source_recurring_id = db.Column(
        db.Integer, db.ForeignKey("recurring_expenses.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)


class RecurringCadence(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class RecurringExpense(db.Model):
    __tablename__ = "recurring_expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    expense_type = db.Column(db.String(20), default="EXPENSE", nullable=False)
    notes = db.Column(db.String(500), nullable=False)
    cadence = db.Column(SAEnum(RecurringCadence), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class BillCadence(str, Enum):
    MONTHLY = "MONTHLY"
    WEEKLY = "WEEKLY"
    YEARLY = "YEARLY"
    ONCE = "ONCE"


class Bill(db.Model):
    __tablename__ = "bills"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    next_due_date = db.Column(db.Date, nullable=False)
    cadence = db.Column(SAEnum(BillCadence), nullable=False)
    autopay_enabled = db.Column(db.Boolean, default=False, nullable=False)
    channel_whatsapp = db.Column(db.Boolean, default=False, nullable=False)
    channel_email = db.Column(db.Boolean, default=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Reminder(db.Model):
    __tablename__ = "reminders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"), nullable=True)
    message = db.Column(db.String(500), nullable=False)
    send_at = db.Column(db.DateTime, nullable=False)
    sent = db.Column(db.Boolean, default=False, nullable=False)
    channel = db.Column(db.String(20), default="email", nullable=False)


class AdImpression(db.Model):
    __tablename__ = "ad_impressions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    placement = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SubscriptionPlan(db.Model):
    __tablename__ = "subscription_plans"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)
    interval = db.Column(db.String(20), default="monthly", nullable=False)


class UserSubscription(db.Model):
    __tablename__ = "user_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan_id = db.Column(
        db.Integer, db.ForeignKey("subscription_plans.id"), nullable=False
    )
    active = db.Column(db.Boolean, default=False, nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class LoginEventType(str, Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    BRUTE_FORCE_BLOCKED = "brute_force_blocked"
    SUSPICIOUS_LOGIN = "suspicious_login"


class LoginEvent(db.Model):
    """Track all login-related events for anomaly detection."""
    __tablename__ = "login_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    event_type = db.Column(db.String(30), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv6 max length
    user_agent = db.Column(db.String(500), nullable=True)
    device_fingerprint = db.Column(db.String(128), nullable=True)
    location_country = db.Column(db.String(100), nullable=True)
    location_city = db.Column(db.String(100), nullable=True)
    risk_score = db.Column(db.Numeric(3, 2), default=0.0, nullable=False)
    risk_factors = db.Column(db.Text, nullable=True)  # JSON array of risk factors
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "device_fingerprint": self.device_fingerprint,
            "location_country": self.location_country,
            "location_city": self.location_city,
            "risk_score": float(self.risk_score) if self.risk_score else 0.0,
            "risk_factors": json.loads(self.risk_factors) if self.risk_factors else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class SecurityAlert(db.Model):
    """Security alerts generated from suspicious activities."""
    __tablename__ = "security_alerts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default=AlertSeverity.MEDIUM.value, nullable=False)
    status = db.Column(db.String(20), default=AlertStatus.ACTIVE.value, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    login_event_id = db.Column(db.Integer, db.ForeignKey("login_events.id"), nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "login_event_id": self.login_event_id,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TrustedDevice(db.Model):
    """Manage trusted devices for users."""
    __tablename__ = "trusted_devices"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    device_fingerprint = db.Column(db.String(128), nullable=False)
    device_name = db.Column(db.String(100), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    last_used_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    trusted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_fingerprint": self.device_fingerprint[:16] + "..." if self.device_fingerprint else None,
            "device_name": self.device_name,
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "trusted_at": self.trusted_at.isoformat() if self.trusted_at else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
