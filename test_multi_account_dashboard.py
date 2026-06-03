"""
Tests for multi-account financial overview dashboard.
"""
import pytest
from datetime import datetime, date
from decimal import Decimal
from app.services.multi_account import (
    get_financial_summary,
    get_multi_account_summary,
)
from app.models import User, Expense, Category
from app.extensions import db


class TestGetFinancialSummary:
    """Test get_financial_summary function."""

    def test_no_expenses(self, app, db, sample_user):
        """Test with no expenses."""
        with app.app_context():
            result = get_financial_summary(user_id=sample_user.id)
            
            assert result["total_spent"] == 0
            assert result["transaction_count"] == 0
            assert result["average_transaction"] == 0
            assert result["by_category"] == {}
            assert result["monthly_trend"] == {}

    def test_with_expenses(self, app, db, sample_user, sample_category):
        """Test with some expenses."""
        with app.app_context():
            # Create expenses
            exp1 = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("100.50"),
                spent_at=datetime(2024, 1, 15)
            )
            exp2 = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("200.75"),
                spent_at=datetime(2024, 2, 20)
            )
            db.session.add_all([exp1, exp2])
            db.session.commit()
            
            result = get_financial_summary(user_id=sample_user.id)
            
            assert result["total_spent"] == 301.25
            assert result["transaction_count"] == 2
            assert abs(result["average_transaction"] - 150.625) < 0.01
            assert sample_category.name in result["by_category"]

    def test_category_filter(self, app, db, sample_user):
        """Test filtering by category."""
        with app.app_context():
            cat1 = Category(name="Food", user_id=sample_user.id)
            cat2 = Category(name="Transport", user_id=sample_user.id)
            db.session.add_all([cat1, cat2])
            db.session.flush()
            
            exp1 = Expense(
                user_id=sample_user.id,
                category_id=cat1.id,
                amount=Decimal("50.00"),
                spent_at=datetime(2024, 1, 10)
            )
            exp2 = Expense(
                user_id=sample_user.id,
                category_id=cat2.id,
                amount=Decimal("30.00"),
                spent_at=datetime(2024, 1, 20)
            )
            db.session.add_all([exp1, exp2])
            db.session.commit()
            
            result = get_financial_summary(
                user_id=sample_user.id,
                category_ids=[cat1.id]
            )
            
            assert result["total_spent"] == 50.00
            assert result["transaction_count"] == 1
            assert "Food" in result["by_category"]
            assert "Transport" not in result["by_category"]

    def test_date_range_filter(self, app, db, sample_user, sample_category):
        """Test filtering by date range."""
        with app.app_context():
            exp1 = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("100.00"),
                spent_at=datetime(2024, 1, 15)
            )
            exp2 = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("200.00"),
                spent_at=datetime(2024, 6, 15)
            )
            db.session.add_all([exp1, exp2])
            db.session.commit()
            
            result = get_financial_summary(
                user_id=sample_user.id,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 3, 31)
            )
            
            assert result["total_spent"] == 100.00
            assert result["transaction_count"] == 1

    def test_monthly_trend(self, app, db, sample_user, sample_category):
        """Test monthly trend calculation."""
        with app.app_context():
            exp1 = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("100.00"),
                spent_at=datetime(2024, 1, 15)
            )
            exp2 = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("200.00"),
                spent_at=datetime(2024, 1, 25)
            )
            exp3 = Expense(
                user_id=sample_user.id,
                category_id=sample_category.id,
                amount=Decimal("150.00"),
                spent_at=datetime(2024, 2, 10)
            )
            db.session.add_all([exp1, exp2, exp3])
            db.session.commit()
            
            result = get_financial_summary(user_id=sample_user.id)
            
            assert "2024-01" in result["monthly_trend"]
            assert "2024-02" in result["monthly_trend"]
            assert result["monthly_trend"]["2024-01"] == 300.00
            assert result["monthly_trend"]["2024-02"] == 150.00


class TestBackwardCompatibility:
    """Test backward compatibility alias."""

    def test_alias_works(self):
        """Test that get_multi_account_summary is an alias."""
        assert get_multi_account_summary is get_financial_summary


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


@pytest.fixture
def sample_category(app, db, sample_user):
    """Create a sample category."""
    with app.app_context():
        category = Category(name="General", user_id=sample_user.id)
        db.session.add(category)
        db.session.commit()
        return category
