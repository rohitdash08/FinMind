"""
Tests for notification priority and grouping system.
"""
import pytest
from datetime import datetime, timedelta
from app.services.notification_priority import (
    Priority,
    NotificationGroup,
    create_notification,
    priority_order,
    get_user_notifications,
)
from app.extensions import db


class TestPriorityEnum:
    """Test Priority enum values."""

    def test_priority_values(self):
        assert Priority.LOW.value == "low"
        assert Priority.NORMAL.value == "normal"
        assert Priority.HIGH.value == "high"
        assert Priority.URGENT.value == "urgent"

    def test_priority_order(self):
        assert priority_order("low") < priority_order("normal")
        assert priority_order("normal") < priority_order("high")
        assert priority_order("high") < priority_order("urgent")


class TestNotificationGroup:
    """Test NotificationGroup model."""

    def test_create_notification_group(self, app, db):
        with app.app_context():
            group = NotificationGroup(
                user_id=1,
                group_key="test_group",
                priority=Priority.NORMAL.value,
                count=1,
                last_message="Test message",
            )
            db.session.add(group)
            db.session.commit()

            saved = NotificationGroup.query.filter_by(
                user_id=1, group_key="test_group"
            ).first()
            assert saved is not None
            assert saved.count == 1
            assert saved.priority == Priority.NORMAL.value

    def test_notification_group_defaults(self, app, db):
        with app.app_context():
            group = NotificationGroup(user_id=1, group_key="test_defaults")
            db.session.add(group)
            db.session.commit()

            assert group.count == 1
            assert group.priority == Priority.NORMAL.value
            assert group.created_at is not None
            assert group.updated_at is not None


class TestCreateNotification:
    """Test create_notification function."""

    def test_create_new_notification(self, app, db):
        with app.app_context():
            result = create_notification(
                user_id=1,
                message="Test notification",
                priority="normal",
                group_key="test_group",
            )

            assert result["grouped"] is False
            assert result["count"] == 1

            # Verify in database
            group = NotificationGroup.query.filter_by(
                user_id=1, group_key="test_group"
            ).first()
            assert group is not None
            assert group.last_message == "Test notification"

    def test_group_existing_notification(self, app, db):
        with app.app_context():
            # Create first notification
            create_notification(
                user_id=1,
                message="First message",
                priority="normal",
                group_key="test_group",
            )

            # Create second notification with same group_key
            result = create_notification(
                user_id=1,
                message="Second message",
                priority="high",
                group_key="test_group",
            )

            assert result["grouped"] is True
            assert result["count"] == 2

            # Verify priority escalated
            group = NotificationGroup.query.filter_by(
                user_id=1, group_key="test_group"
            ).first()
            assert group.priority == Priority.HIGH.value
            assert group.last_message == "Second message"

    def test_create_notification_without_group(self, app, db):
        with app.app_context():
            result = create_notification(
                user_id=1,
                message="Ungrouped notification",
                priority="urgent",
            )

            assert result["grouped"] is False
            assert result["count"] == 1

    def test_priority_escalation(self, app, db):
        with app.app_context():
            # Create with low priority
            create_notification(
                user_id=1,
                message="Low priority",
                priority="low",
                group_key="test_escalation",
            )

            # Escalate to high priority
            create_notification(
                user_id=1,
                message="High priority",
                priority="high",
                group_key="test_escalation",
            )

            group = NotificationGroup.query.filter_by(
                user_id=1, group_key="test_escalation"
            ).first()
            assert group.priority == Priority.HIGH.value

    def test_no_de_escalation(self, app, db):
        with app.app_context():
            # Create with high priority
            create_notification(
                user_id=1,
                message="High priority",
                priority="high",
                group_key="test_no_deescalation",
            )

            # Try to de-escalate to low priority
            create_notification(
                user_id=1,
                message="Low priority",
                priority="low",
                group_key="test_no_deescalation",
            )

            group = NotificationGroup.query.filter_by(
                user_id=1, group_key="test_no_deescalation"
            ).first()
            # Priority should remain high
            assert group.priority == Priority.HIGH.value


class TestGetUserNotifications:
    """Test get_user_notifications function."""

    def test_get_user_notifications(self, app, db):
        with app.app_context():
            # Create some notifications
            create_notification(
                user_id=1,
                message="Message 1",
                group_key="group_1",
            )
            create_notification(
                user_id=1,
                message="Message 2",
                group_key="group_2",
            )

            notifications = get_user_notifications(user_id=1)
            assert len(notifications) == 2

    def test_get_notifications_empty(self, app, db):
        with app.app_context():
            notifications = get_user_notifications(user_id=999)
            assert len(notifications) == 0


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
