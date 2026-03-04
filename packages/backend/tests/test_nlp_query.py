"""
Tests for Natural Language Query endpoint
"""
import pytest
from datetime import datetime, timedelta


def test_nlp_query_last_quarter(client, auth_headers, sample_user, sample_expenses):
    """Test querying expenses for last quarter"""
    response = client.post(
        "/query",
        json={"query": "How much did I spend on food last quarter?"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert "answer" in data
    assert "total_amount" in data
    assert "currency" in data
    assert "transaction_count" in data
    assert "date_range" in data
    assert "source_data" in data
    
    assert data["currency"] == "INR"
    assert isinstance(data["total_amount"], (int, float))
    assert isinstance(data["transaction_count"], int)


def test_nlp_query_this_month(client, auth_headers, sample_user):
    """Test querying expenses for this month"""
    response = client.post(
        "/query",
        json={"query": "How much did I spend this month?"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert "answer" in data
    assert "date_range" in data
    
    # Verify date range is current month
    today = datetime.now().date()
    start_of_month = datetime(today.year, today.month, 1).date()
    
    assert data["date_range"]["start"] == start_of_month.isoformat()
    assert data["date_range"]["end"] == today.isoformat()


def test_nlp_query_with_category(client, auth_headers, sample_user, sample_category):
    """Test querying expenses with category filter"""
    response = client.post(
        "/query",
        json={"query": "How much did I spend on food last month?"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert "category" in data
    # Category might be None if no matching expenses


def test_nlp_query_missing_query(client, auth_headers):
    """Test error when query is missing"""
    response = client.post(
        "/query",
        json={},
        headers=auth_headers
    )
    
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_nlp_query_empty_query(client, auth_headers):
    """Test error when query is empty"""
    response = client.post(
        "/query",
        json={"query": ""},
        headers=auth_headers
    )
    
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_nlp_query_unauthorized(client):
    """Test that endpoint requires authentication"""
    response = client.post(
        "/query",
        json={"query": "How much did I spend?"}
    )
    
    assert response.status_code == 401


def test_nlp_query_last_year(client, auth_headers, sample_user):
    """Test querying expenses for last year"""
    response = client.post(
        "/query",
        json={"query": "What did I spend last year?"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.get_json()
    
    today = datetime.now().date()
    last_year = today.year - 1
    
    assert data["date_range"]["start"] == f"{last_year}-01-01"
    assert data["date_range"]["end"] == f"{last_year}-12-31"


def test_nlp_query_last_30_days(client, auth_headers, sample_user):
    """Test querying expenses for last 30 days"""
    response = client.post(
        "/query",
        json={"query": "How much did I spend in the last 30 days?"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.get_json()
    
    today = datetime.now().date()
    start = (today - timedelta(days=30)).date()
    
    assert data["date_range"]["start"] == start.isoformat()
    assert data["date_range"]["end"] == today.isoformat()
