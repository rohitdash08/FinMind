import pytest
from app.services.explainable_insights import ExplainableInsightsService, _transactions

@pytest.fixture(autouse=True)
def clear_data():
    _transactions.clear()
    yield
    _transactions.clear()

@pytest.fixture
def svc():
    return ExplainableInsightsService()

def add_txn(user_id, date_str, amount, category="food"):
    _transactions[user_id].append({"date": date_str, "amount": amount, "category": category})

def test_top_category_insight(svc):
    add_txn("u1", "2026-04-01T00:00:00", 300, "rent")
    add_txn("u1", "2026-04-05T00:00:00", 50, "food")
    result = svc.get_insights("u1", 2026, 4)
    top = next(i for i in result["insights"] if i["type"] == "top_category")
    assert top["category"] == "rent"
    assert top["amount"] == 300

def test_mom_change_increase(svc):
    add_txn("u2", "2026-03-10T00:00:00", 100, "food")
    add_txn("u2", "2026-04-10T00:00:00", 200, "food")
    result = svc.get_insights("u2", 2026, 4)
    mom = next((i for i in result["insights"] if i["type"] == "mom_change"), None)
    assert mom is not None
    assert mom["change_pct"] == 100.0

def test_category_spike(svc):
    add_txn("u3", "2026-03-01T00:00:00", 100, "entertainment")
    add_txn("u3", "2026-04-01T00:00:00", 200, "entertainment")
    result = svc.get_insights("u3", 2026, 4)
    spike = next((i for i in result["insights"] if i["type"] == "category_spike"), None)
    assert spike is not None
    assert spike["spike_pct"] == 100.0

def test_large_transaction(svc):
    add_txn("u4", "2026-04-15T00:00:00", 500, "travel")
    result = svc.get_insights("u4", 2026, 4)
    large = next((i for i in result["insights"] if i["type"] == "large_transaction"), None)
    assert large is not None
    assert large["amount"] == 500

def test_no_insights_for_empty(svc):
    result = svc.get_insights("u_empty", 2026, 4)
    assert result["total_spending"] == 0
    assert isinstance(result["insights"], list)