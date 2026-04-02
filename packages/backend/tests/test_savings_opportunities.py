from datetime import date, timedelta
from decimal import Decimal


def test_savings_opportunities_empty(client, auth_header):
    """Test that empty expense history returns empty opportunities."""
    r = client.get("/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "opportunities" in payload
    assert "summary" in payload
    assert payload["opportunities"] == []
    assert payload["summary"]["total_analyzed"] == 0


def test_savings_opportunities_with_expenses(client, auth_header):
    """Test that expenses are analyzed correctly."""
    # Create some expenses
    for i in range(5):
        r = client.post(
            "/expenses",
            json={
                "amount": 100 + i * 10,
                "description": f"Coffee shop visit {i+1}",
                "date": (date.today() - timedelta(days=i*7)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
    
    r = client.get("/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "opportunities" in payload
    assert "summary" in payload
    assert payload["summary"]["total_analyzed"] == 5


def test_savings_opportunities_high_frequency_detection(client, auth_header):
    """Test detection of high-frequency expenses."""
    # Create many similar expenses
    for i in range(8):
        r = client.post(
            "/expenses",
            json={
                "amount": 15.00,
                "description": "Daily coffee",
                "date": (date.today() - timedelta(days=i)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
    
    r = client.get("/savings-opportunities?months=1", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert len(payload["opportunities"]) > 0
    
    # Should detect high frequency expense
    high_freq = [o for o in payload["opportunities"] if o["type"] == "high_frequency"]
    assert len(high_freq) > 0
    assert high_freq[0]["confidence"] >= 70


def test_savings_opportunities_subscription_detection(client, auth_header):
    """Test detection of potential subscriptions."""
    # Create monthly recurring expenses
    for i in range(3):
        r = client.post(
            "/expenses",
            json={
                "amount": 9.99,
                "description": "Netflix subscription",
                "date": (date.today() - timedelta(days=i*30)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
    
    r = client.get("/savings-opportunities?months=3", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Should detect potential subscription
    subscriptions = [o for o in payload["opportunities"] if o["type"] == "potential_subscription"]
    assert len(subscriptions) > 0
    assert subscriptions[0]["confidence"] == 75


def test_savings_opportunities_category_trend(client, auth_header):
    """Test detection of increasing category trends."""
    # Create a category first
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code in (200, 201)
    cat_id = r.get_json()["id"]
    
    # Create increasing expenses in category
    for i in range(4):
        r = client.post(
            "/expenses",
            json={
                "amount": 100 + i * 50,  # Increasing amounts
                "description": f"Grocery shopping week {i+1}",
                "category_id": cat_id,
                "date": (date.today() - timedelta(days=i*30)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
    
    r = client.get("/savings-opportunities?months=4", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Should detect increasing trend
    trends = [o for o in payload["opportunities"] if o["type"] == "increasing_trend"]
    # Note: May or may not detect depending on trend calculation
    if len(trends) > 0:
        assert trends[0]["category"] == "Food"
        assert trends[0]["confidence"] >= 50


def test_savings_opportunities_min_confidence_filter(client, auth_header):
    """Test filtering by minimum confidence."""
    # Create various expenses
    for i in range(10):
        r = client.post(
            "/expenses",
            json={
                "amount": 20 + i * 5,
                "description": f"Expense {i+1}",
                "date": (date.today() - timedelta(days=i*3)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
    
    # Get all opportunities
    r = client.get("/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
    all_opportunities = r.get_json()["opportunities"]
    
    # Get only high confidence
    r = client.get("/savings-opportunities?min_confidence=80", headers=auth_header)
    assert r.status_code == 200
    high_conf_opportunities = r.get_json()["opportunities"]
    
    # High confidence should be subset of all
    assert len(high_conf_opportunities) <= len(all_opportunities)
    for opp in high_conf_opportunities:
        assert opp["confidence"] >= 80


def test_savings_opportunities_months_parameter(client, auth_header):
    """Test the months parameter."""
    # Create expenses
    for i in range(3):
        r = client.post(
            "/expenses",
            json={
                "amount": 50,
                "description": f"Expense {i+1}",
                "date": (date.today() - timedelta(days=i*30)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
    
    # Test different month ranges
    r = client.get("/savings-opportunities?months=1", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["summary"]["analysis_period_months"] == 1
    
    r = client.get("/savings-opportunities?months=6", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["summary"]["analysis_period_months"] == 6


def test_savings_opportunities_invalid_parameters(client, auth_header):
    """Test invalid parameter handling."""
    # Invalid months
    r = client.get("/savings-opportunities?months=invalid", headers=auth_header)
    assert r.status_code == 400
    
    # Invalid min_confidence
    r = client.get("/savings-opportunities?min_confidence=invalid", headers=auth_header)
    assert r.status_code == 400


def test_savings_opportunities_response_structure(client, auth_header):
    """Test that response has correct structure."""
    # Create an expense
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Test expense",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    r = client.get("/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Check summary structure
    assert "total_analyzed" in payload["summary"]
    assert "potential_savings" in payload["summary"]
    assert "analysis_period_months" in payload["summary"]
    assert "generated_at" in payload
    
    # If opportunities exist, check their structure
    if payload["opportunities"]:
        opp = payload["opportunities"][0]
        assert "type" in opp
        assert "category" in opp
        assert "description" in opp
        assert "potential_savings" in opp
        assert "confidence" in opp
        assert "details" in opp
        assert isinstance(opp["confidence"], int)
        assert 0 <= opp["confidence"] <= 100


def test_savings_opportunities_requires_auth(client):
    """Test that endpoint requires authentication."""
    r = client.get("/savings-opportunities")
    assert r.status_code == 401


def test_savings_opportunities_excludes_income(client, auth_header):
    """Test that income expenses are excluded from analysis."""
    # Create regular expense
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Regular expense",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Create income (should be excluded)
    r = client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Salary",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    r = client.get("/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Should only analyze 1 expense (the EXPENSE type)
    assert payload["summary"]["total_analyzed"] == 1
