"""
Tests for subscription detection and management.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from app import create_app
from app.extensions import db, redis_client
from app.models import Expense, Subscription, SubscriptionStatus, SubscriptionCadence, User, Category
from app.services import cache


@pytest.fixture(autouse=True)
def mock_redis_operations(monkeypatch):
    """Mock Redis operations to avoid connection errors in tests."""
    # Mock redis_client methods
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.scan.return_value = (0, [])
    mock_redis.flushdb.return_value = True
    
    monkeypatch.setattr("app.extensions.redis_client", mock_redis)
    
    # Also mock cache functions
    def mock_cache_delete_patterns(patterns):
        pass
    
    monkeypatch.setattr(cache, "cache_delete_patterns", mock_cache_delete_patterns)


def _create_user_and_auth(client, email="test@example.com", password="password123"):
    """Helper to create user and return auth header."""
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (200, 201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    return r.get_json()[0]["id"]


def test_subscription_detection_weekly_pattern(client, auth_header):
    """Test detection of weekly subscription pattern."""
    cat_id = _create_category(client, auth_header, name="Streaming")
    
    # Create weekly expenses for Netflix: same amount, ~7 days apart
    base_date = date(2026, 1, 1)
    amounts = [15.99, 15.99, 15.99, 15.99]  # 4 occurrences
    
    for i, amount in enumerate(amounts):
        expense_date = base_date + timedelta(days=7 * i)
        r = client.post("/expenses", json={
            "amount": float(amount),
            "currency": "USD",
            "category_id": cat_id,
            "description": "Netflix",
            "date": expense_date.isoformat(),
        }, headers=auth_header)
        assert r.status_code == 201
    
    # Trigger detection
    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code in (201, 200)
    result = r.get_json()
    
    # Should detect at least one subscription
    assert result["detected"] >= 1
    subs = result["subscriptions"]
    
    # Find Netflix subscription
    netflix_sub = next((s for s in subs if "netflix" in s["merchant_name"].lower()), None)
    assert netflix_sub is not None
    assert netflix_sub["detected_cadence"] == "WEEKLY"
    assert netflix_sub["confidence_score"] >= 0.7
    assert netflix_sub["occurrence_count"] == 4
    assert netflix_sub["status"] == "DETECTED"


def test_subscription_detection_monthly_pattern(client, auth_header):
    """Test detection of monthly subscription pattern."""
    cat_id = _create_category(client, auth_header, name="Utilities")
    
    # Create monthly expenses for Spotify: same amount, ~30 days apart
    base_date = date(2026, 1, 15)
    amounts = [9.99, 9.99, 9.99]
    
    for i, amount in enumerate(amounts):
        # Add some day variance to test robustness
        expense_date = base_date + timedelta(days=30 * i + (2 if i > 0 else 0))
        r = client.post("/expenses", json={
            "amount": float(amount),
            "currency": "USD",
            "category_id": cat_id,
            "description": "Spotify",
            "date": expense_date.isoformat(),
        }, headers=auth_header)
        assert r.status_code == 201
    
    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code in (201, 200)
    result = r.get_json()
    
    spotify_sub = next((s for s in result["subscriptions"] if "spotify" in s["merchant_name"].lower()), None)
    assert spotify_sub is not None
    assert spotify_sub["detected_cadence"] == "MONTHLY"
    assert spotify_sub["confidence_score"] >= 0.7


def test_subscription_detection_insufficient_data(client, auth_header):
    """Test that detection requires minimum occurrences."""
    cat_id = _create_category(client, auth_header)
    
    # Only 2 occurrences - should not create subscription
    base_date = date(2026, 1, 1)
    for i in range(2):
        r = client.post("/expenses", json={
            "amount": 10.0,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Rare Service",
            "date": (base_date + timedelta(days=30 * i)).isoformat(),
        }, headers=auth_header)
        assert r.status_code == 201
    
    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code in (201, 200)
    result = r.get_json()
    
    # Should not detect (insufficient data)
    assert result["detected"] == 0


def test_subscription_list_empty(client, auth_header):
    """Test listing subscriptions when none exist."""
    r = client.get("/subscriptions", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_subscription_confirm_and_dismiss(client, auth_header):
    """Test confirming and dismissing a detected subscription."""
    cat_id = _create_category(client, auth_header, name="Subscriptions")
    
    # Create expenses for a clear weekly pattern
    base_date = date(2026, 1, 1)
    for i in range(4):
        r = client.post("/expenses", json={
            "amount": 19.99,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Hulu",
            "date": (base_date + timedelta(days=7 * i)).isoformat(),
        }, headers=auth_header)
        assert r.status_code == 201
    
    # Detect
    r = client.post("/subscriptions/detect", headers=auth_header)
    assert r.status_code in (201, 200)
    subs = r.get_json()["subscriptions"]
    hulu_sub = next(s for s in subs if "hulu" in s["merchant_name"].lower())
    sub_id = hulu_sub["id"]
    assert hulu_sub["status"] == "DETECTED"
    
    # Confirm
    r = client.post(f"/subscriptions/{sub_id}/confirm", headers=auth_header)
    assert r.status_code == 200
    confirmed = r.get_json()
    assert confirmed["status"] == "CONFIRMED"
    
    # Try to confirm again - should fail
    r = client.post(f"/subscriptions/{sub_id}/confirm", headers=auth_header)
    assert r.status_code == 400
    
    # Dismiss
    r = client.post(f"/subscriptions/{sub_id}/dismiss", headers=auth_header)
    assert r.status_code == 200
    dismissed = r.get_json()
    assert dismissed["status"] == "DISMISSED"
    
    # Delete (soft delete)
    r = client.delete(f"/subscriptions/{sub_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"


def test_subscription_filter_by_status(client, auth_header):
    """Test filtering subscriptions by status."""
    cat_id = _create_category(client, auth_header)
    
    # Create two different patterns
    base_date = date(2026, 1, 1)
    
    # Pattern 1: weekly (will be DETECTED)
    for i in range(4):
        client.post("/expenses", json={
            "amount": 10.0,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Service A",
            "date": (base_date + timedelta(days=7 * i)).isoformat(),
        }, headers=auth_header)
    
    # Pattern 2: monthly (will be DETECTED)
    for i in range(4):
        client.post("/expenses", json={
            "amount": 20.0,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Service B",
            "date": (base_date + timedelta(days=30 * i)).isoformat(),
        }, headers=auth_header)
    
    client.post("/subscriptions/detect", headers=auth_header)
    
    # List all
    r = client.get("/subscriptions", headers=auth_header)
    assert r.status_code == 200
    all_subs = r.get_json()
    assert len(all_subs) >= 2
    
    # Filter DETECTED
    r = client.get("/subscriptions?status=DETECTED", headers=auth_header)
    assert r.status_code == 200
    detected = r.get_json()
    assert all(s["status"] == "DETECTED" for s in detected)


def test_refresh_predictions(client, auth_header):
    """Test refreshing next_predicted_date for confirmed subscriptions."""
    cat_id = _create_category(client, auth_header)
    
    # Create weekly pattern and detect
    base_date = date(2026, 1, 1)
    for i in range(4):
        client.post("/expenses", json={
            "amount": 15.0,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Test Sub",
            "date": (base_date + timedelta(days=7 * i)).isoformat(),
        }, headers=auth_header)
    
    r = client.post("/subscriptions/detect", headers=auth_header)
    subs = r.get_json()["subscriptions"]
    sub_id = subs[0]["id"]
    
    # Confirm it
    client.post(f"/subscriptions/{sub_id}/confirm", headers=auth_header)
    
    # Refresh predictions
    r = client.get("/subscriptions/predictions/refresh", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "predictions refreshed"
    
    # Verify next_predicted_date is set
    r = client.get(f"/subscriptions/{sub_id}", headers=auth_header)
    # Note: we'd need a GET /subscriptions/{id} endpoint, but for now we check via list
    r = client.get("/subscriptions?status=CONFIRMED", headers=auth_header)
    confirmed = r.get_json()
    assert len(confirmed) > 0
    assert confirmed[0]["next_predicted_date"] is not None


def test_detection_ignores_different_amounts(client, auth_header):
    """Test that expenses with varying amounts are less likely to be detected."""
    cat_id = _create_category(client, auth_header)
    
    base_date = date(2026, 1, 1)
    amounts = [10.0, 15.0, 12.0, 20.0]  # High variance
    
    for i, amount in enumerate(amounts):
        client.post("/expenses", json={
            "amount": amount,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Variable Service",
            "date": (base_date + timedelta(days=7 * i)).isoformat(),
        }, headers=auth_header)
    
    r = client.post("/subscriptions/detect", headers=auth_header)
    result = r.get_json()
    
    # Might detect but confidence should be lower
    if result["detected"] > 0:
        sub = next((s for s in result["subscriptions"] if "variable" in s["merchant_name"].lower()), None)
        if sub:
            assert sub["confidence_score"] < 0.8
            assert sub["amount_variance"] is not None


def test_merchant_name_normalization(client, auth_header):
    """Test that similar merchant names are grouped."""
    cat_id = _create_category(client, auth_header)
    
    base_date = date(2026, 1, 1)
    # Slight variations in name
    names = ["Netflix", "Netflix ", " NETFLIX", "netflix"]
    
    for i, name in enumerate(names):
        client.post("/expenses", json={
            "amount": 15.99,
            "currency": "USD",
            "category_id": cat_id,
            "description": name,
            "date": (base_date + timedelta(days=7 * i)).isoformat(),
        }, headers=auth_header)
    
    r = client.post("/subscriptions/detect", headers=auth_header)
    result = r.get_json()
    
    # Should group them as one subscription
    netflix_subs = [s for s in result["subscriptions"] if "netflix" in s["merchant_name"].lower()]
    assert len(netflix_subs) == 1
    assert netflix_subs[0]["occurrence_count"] == 4