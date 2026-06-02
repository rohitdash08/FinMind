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
from app.extensions import db


class TestReminderDelivery:
    """Test ReminderDelivery model."""

    def test_create_delivery(self, app, db):
        with app.app_context():
            delivery = ReminderDelivery(
                reminder_id=1,
                user_id=1,
                channel="email",
                status="sent",
                latency_ms=150,
            )
            db.session.add(delivery)
            db.session.commit()

            saved = ReminderDelivery.query.get(delivery.id)
            assert saved is not None
            assert saved.reminder_id == 1
            assert saved.user_id == 1
            assert saved.channel == "email"
            assert saved.status == "sent"
            assert saved.latency_ms == 150

    def test_delivery_defaults(self, app, db):
        with app.app_context():
            delivery = ReminderDelivery(
                reminder_id=1,
                user_id=1,
                channel="push",
                status="delivered",
            )
            db.session.add(delivery)
            db.session.commit()

            assert delivery.created_at is not None
            assert delivery.latency_ms is None
            assert delivery.error is None


class TestTrackDelivery:
    """Test track_delivery function."""

    def test_track_delivery_success(self, app, db):
        with app.app_context():
            track_delivery(
                reminder_id=1,
                user_id=1,
                channel="email",
                status="sent",
                latency_ms=200,
            )

            delivery = ReminderDelivery.query.filter_by(
                reminder_id=1, user_id=1
            ).first()
            assert delivery is not None
            assert delivery.status == "sent"
            assert delivery.latency_ms == 200

    def test_track_delivery_with_error(self, app, db):
        with app.app_context():
            track_delivery(
                reminder_id=2,
                user_id=1,
                channel="sms",
                status="failed",
                error="Network timeout",
            )

            delivery = ReminderDelivery.query.filter_by(
                reminder_id=2, user_id=1
            ).first()
            assert delivery is not None
            assert delivery.status == "failed"
            assert delivery.error == "Network timeout"

    def test_track_multiple_deliveries(self, app, db):
        with app.app_context():
            # Track multiple deliveries
            for i in range(5):
                track_delivery(
                    reminder_id=i + 1,
                    user_id=1,
                    channel="email",
                    status="sent" if i % 2 == 0 else "failed",
                    latency_ms=100 + i * 50,
                )

            deliveries = ReminderDelivery.query.filter_by(user_id=1).all()
            assert len(deliveries) == 5


class TestGetDeliveryMetrics:
    """Test get_delivery_metrics function."""

    def test_empty_metrics(self, app, db):
        with app.app_context():
            metrics = get_delivery_metrics(user_id=999)
            
            assert metrics["total"] == 0
            assert metrics["success_rate"] == 0
            assert metrics["avg_latency_ms"] == 0

    def test_all_successful(self, app, db):
        with app.app_context():
            # Add successful deliveries
            for i in range(3):
                track_delivery(
                    reminder_id=i + 1,
                    user_id=1,
                    channel="email",
                    status="sent",
                    latency_ms=100 + i * 50,
                )

            metrics = get_delivery_metrics(user_id=1)
            
            assert metrics["total"] == 3
            assert metrics["success_rate"] == 1.0
            assert metrics["avg_latency_ms"] == 150  # (100 + 150 + 200) / 3

    def test_mixed_status(self, app, db):
        with app.app_context():
            # Add mixed deliveries
            track_delivery(reminder_id=1, user_id=1, channel="email", status="sent", latency_ms=100)
            track_delivery(reminder_id=2, user_id=1, channel="email", status="delivered", latency_ms=200)
            track_delivery(reminder_id=3, user_id=1, channel="email", status="failed", latency_ms=None)

            metrics = get_delivery_metrics(user_id=1)
            
            assert metrics["total"] == 3
            assert metrics["success_rate"] == pytest.approx(2/3, abs=0.01)
            assert metrics["avg_latency_ms"] == 150  # (100 + 200) / 2

    def test_date_filtering(self, app, db):
        with app.app_context():
            # Add old delivery (outside 30-day window)
            old_delivery = ReminderDelivery(
                reminder_id=1,
                user_id=1,
                channel="email",
                status="sent",
                latency_ms=100,
                created_at=datetime.utcnow() - timedelta(days=31),
            )
            db.session.add(old_delivery)
            db.session.commit()

            # Add recent delivery
            track_delivery(
                reminder_id=2,
                user_id=1,
                channel="email",
                status="sent",
                latency_ms=200,
            )

            metrics = get_delivery_metrics(user_id=1, days=30)
            
            # Should only count recent delivery
            assert metrics["total"] == 1
            assert metrics["avg_latency_ms"] == 200

    def test_by_channel_breakdown(self, app, db):
        with app.app_context():
            # Add deliveries for different channels
            track_delivery(reminder_id=1, user_id=1, channel="email", status="sent", latency_ms=100)
            track_delivery(reminder_id=2, user_id=1, channel="push", status="sent", latency_ms=50)
            track_delivery(reminder_id=3, user_id=1, channel="email", status="failed", latency_ms=None)

            metrics = get_delivery_metrics(user_id=1)
            
            assert "by_channel" in metrics
            assert "email" in metrics["by_channel"]
            assert "push" in metrics["by_channel"]
            assert metrics["by_channel"]["email"]["total"] == 2
            assert metrics["by_channel"]["push"]["total"] == 1

    def test_latency_none_handling(self, app, db):
        with app.app_context():
            # Add delivery with None latency
            track_delivery(
                reminder_id=1,
                user_id=1,
                channel="sms",
                status="sent",
                latency_ms=None,
            )

            metrics = get_delivery_metrics(user_id=1)
            
            # Should handle None latency gracefully
            assert metrics["avg_latency_ms"] == 0


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
