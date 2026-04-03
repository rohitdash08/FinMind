import pytest
from datetime import datetime, timedelta
from app.services.cashflow_forecast import CashFlowForecastEngine, _transactions, _income_entries

@pytest.fixture(autouse=True)
def clear_data():
    _transactions.clear()
    _income_entries.clear()
    yield
    _transactions.clear()
    _income_entries.clear()

@pytest.fixture
def engine():
    return CashFlowForecastEngine()

def add_txn(user_id, date_str, amount, category="food"):
    _transactions[user_id].append({"date": date_str, "amount": amount, "category": category})

def test_forecast_empty(engine):
    result = engine.forecast("u_empty")
    assert "forecast" in result
    assert result["summary"].get("error") == "insufficient history"

def test_forecast_basic(engine):
    now = datetime.utcnow()
    for i in range(1, 5):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        add_txn("u1", f"{y}-{m:02d}-10T00:00:00", 1000)
        engine.add_income("u1", 2000, f"{y}-{m:02d}-05T00:00:00")
    result = engine.forecast("u1", months_ahead=3, current_balance=500)
    assert len(result["forecast"]) == 3
    for f in result["forecast"]:
        assert "projected_income" in f
        assert "projected_spending" in f
        assert "projected_net" in f
        assert "confidence" in f

def test_forecast_confidence_decreases(engine):
    now = datetime.utcnow()
    for i in range(1, 5):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        add_txn("u2", f"{y}-{m:02d}-10T00:00:00", 500)
        engine.add_income("u2", 1500, f"{y}-{m:02d}-05T00:00:00")
    result = engine.forecast("u2", months_ahead=3)
    forecasts = result["forecast"]
    assert forecasts[0]["confidence"] > forecasts[1]["confidence"]
    assert forecasts[1]["confidence"] > forecasts[2]["confidence"]

def test_positive_cashflow_outlook(engine):
    now = datetime.utcnow()
    for i in range(1, 5):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        add_txn("u3", f"{y}-{m:02d}-10T00:00:00", 500)
        engine.add_income("u3", 3000, f"{y}-{m:02d}-05T00:00:00")
    result = engine.forecast("u3", months_ahead=3)
    assert result["summary"]["outlook"] == "positive"

def test_scenario_bounds(engine):
    now = datetime.utcnow()
    for i in range(1, 5):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        add_txn("u4", f"{y}-{m:02d}-10T00:00:00", 800)
        engine.add_income("u4", 2000, f"{y}-{m:02d}-05T00:00:00")
    result = engine.forecast("u4", months_ahead=2)
    for f in result["forecast"]:
        assert f["scenario"]["optimistic"] >= f["projected_balance"]
        assert f["scenario"]["pessimistic"] <= f["projected_balance"]