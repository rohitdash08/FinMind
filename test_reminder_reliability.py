"""
Tests for reminder reliability tracking and delivery metrics.
"""
import pytest
from datetime import datetime, timedelta
from app.services.reminder_metrics import (
    ReminderDelivery,
    track_delivery,
    get_delivery_metrics,
)
from app.models import User
from app.extensions import db


class TestTrackDelivery:
    """Test track_delivery function."""

    def test_track_successful_delivery(self, app, db, sample_user):
        """Test tracking successful delivery."""
        with app.app_context():
            track_delivery(
                reminder_id=1,
                user_id=sample_user.id,
                channel="email",
                status="sent",
                latency_ms=150
            )
            
            delivery = ReminderDelivery.query.first()
            assert delivery is not None
            assert delivery.reminder_id == 1
            assert delivery.channel == "email"
            assert delivery.status == "sent"
            assert delivery.latency_ms == 150

    def test_track_failed_delivery(self, app, db, sample_user):
        """Test tracking failed delivery."""
        with app.app_context():
            track_delivery(
                reminder_id=1,
                user_id=sample_user.id,
                channel="sms",
                status="failed",
                error="Invalid phone number"
            )
            
            delivery = ReminderDelivery.query.first()
            assert delivery.status == "failed"
            assert delivery.error == "Invalid phone number"

    def test_track_multiple_deliveries(self, app, db, sample_user):
        """Test tracking multiple deliveries."""
        with app.app_context():
            track_delivery(reminder_id=1, user_id=sample_user.id, channel="email", status="sent")
            track_delivery(reminder_id=2, user_id=sample_user.id, channel="push", status="delivered")
            
            count = ReminderDelivery.query.count()
            assert count == 2


class TestGetDeliveryMetrics:
    """Test get_delivery_metrics function."""

    def test_no_deliveries(self, app, db, sample_user):
        """Test metrics with no deliveries."""
        with app.app_context():
            metrics = get_delivery_metrics(user_id=sample_user.id)
            
            assert metrics["total"] == 0
            assert metrics["success_rate"] == 0
            assert metrics["avg_latency_ms"] == 0
            assert metrics["by_channel"] == {}

    def test_all_successful(self, app, db, sample_user):
        """Test metrics with all successful deliveries."""
        with app.app_context():
            track_delivery(reminder_id=1, user_id=sample_user.id, channel="email", status="sent", latency_ms=100)
            track_delivery(reminder_id=2, user_id=sample_user.id, channel="email", status="delivered", latency_ms=200)
            
            metrics = get_delivery_metrics(user_id=sample_user.id)
            
            assert metrics["total"] == 2
            assert metrics["success_rate"] == 100.0
            assert metrics["avg_latency_ms"] == 150.0

    def test_mixed_success_failure(self, app, db, sample_user):
        """Test metrics with mixed success and failure."""
        with app.app_context():
            track_delivery(reminder_id=1, user_id=sample_user.id, channel="email", status="sent", latency_ms=100)
            track_delivery(reminder_id=2, user_id=sample_user.id, channel="email", status="failed", error="timeout")
            
            metrics = get_delivery_metrics(user_id=sample_user.id)
            
            assert metrics["total"] == 2
            assert metrics["success_rate"] == 50.0
            assert metrics["avg_latency_ms"] == 100.0  # Only successful has latency

    def test_by_channel_breakdown(self, app, db, sample_user):
        """Test metrics broken down by channel."""
        with app.app_context():
            track_delivery(reminder_id=1, user_id=sample_user.id, channel="email", status="sent", latency_ms=100)
            track_delivery(reminder_id=2, user_id=sample_user.id, channel="email", status="sent", latency_ms=200)
            track_delivery(reminder_id=3, user_id=sample_user.id, channel="push", status="failed", error="timeout")
            
            metrics = get_delivery_metrics(user_id=sample_user.id)
            
            assert "email" in metrics["by_channel"]
            assert "push" in metrics["by_channel"]
            assert metrics["by_channel"]["email"]["total"] == 2
            assert metrics["by_channel"]["email"]["success_rate"] == 100.0
            assert metrics["by_channel"]["push"]["total"] == 1
            assert metrics["by_channel"]["push"]["success_rate"] == 0.0

    def test_date_filter(self, app, db, sample_user):
        """Test metrics with date filter."""
        with app.app_context():
            # Old delivery (outside date range)
            old_delivery = ReminderDelivery(
                reminder_id=1,
                user_id=sample_user.id,
                channel="email",
                status="sent",
                created_at=datetime.utcnow() - timedelta(days=60)
            )
            db.session.add(old_delivery)
            
            # Recent delivery
            track_delivery(reminder_id=2, user_id=sample_user.id, channel="email", status="sent")
            db.session.commit()
            
            metrics = get_delivery_metrics(user_id=sample_user.id, days=30)
            
            assert metrics["total"] == 1  # Only recent delivery counted


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app
    
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db(app):
    """Create database for testing."""
    with app.app_context():
        yield db


@pytest.fixture
def sample_user(app, db):
    """Create a sample user."""
    with app.app_context():
        user = User(email="test@example.com", currency="USD")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        return user
