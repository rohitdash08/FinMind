import pytest
from datetime import datetime
from app.services.dynamic_budget import DynamicBudgetService, _transactions, _budgets

@pytest.fixture(autouse=True)
def clear_data():
    _transactions.clear()
    _budgets.clear()
    yield
    _transactions.clear()
    _budgets.clear()

@pytest.fixture
def svc():
    return DynamicBudgetService()

def add_txn(user_id, date_str, amount, category):
    _transactions[user_id].append({"date": date_str, "amount": amount, "category": category})

def test_suggest_budgets_empty(svc):
    result = svc.suggest_budgets("u_empty")
    assert "suggestions" in result
    assert result["summary"]["total_avg_spending"] == 0

def test_suggest_budgets_with_history(svc):
    now = datetime.utcnow()
    for i in range(1, 4):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        add_txn("u1", f"{y}-{m:02d}-10T00:00:00", 1000, "rent")
        add_txn("u1", f"{y}-{m:02d}-15T00:00:00", 200, "food")
    result = svc.suggest_budgets("u1")
    cats = {s["category"] for s in result["suggestions"]}
    assert "rent" in cats
    assert "food" in cats
    rent_s = next(s for s in result["suggestions"] if s["category"] == "rent")
    assert rent_s["avg_monthly_spend"] == pytest.approx(1000, rel=0.01)

def test_set_and_get_budget(svc):
    svc.set_budget("u2", "food", 500)
    budgets = svc.get_budgets("u2")
    assert budgets["food"] == 500

def test_budget_status_over(svc):
    now = datetime.utcnow()
    svc.set_budget("u3", "food", 100)
    add_txn("u3", f"{now.year}-{now.month:02d}-05T00:00:00", 150, "food")
    statuses = svc.check_budget_status("u3", now.year, now.month)
    food_status = next(s for s in statuses if s["category"] == "food")
    assert food_status["status"] == "over"
    assert food_status["spent"] == 150

def test_budget_status_ok(svc):
    now = datetime.utcnow()
    svc.set_budget("u4", "entertainment", 200)
    add_txn("u4", f"{now.year}-{now.month:02d}-10T00:00:00", 50, "entertainment")
    statuses = svc.check_budget_status("u4", now.year, now.month)
    s = next(s for s in statuses if s["category"] == "entertainment")
    assert s["status"] == "ok"
    assert s["remaining"] == pytest.approx(150, rel=0.01)

def test_suggest_with_income(svc):
    now = datetime.utcnow()
    for i in range(1, 4):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        add_txn("u5", f"{y}-{m:02d}-10T00:00:00", 1500, "rent")
    result = svc.suggest_budgets("u5", monthly_income=4000)
    assert "savings_rate_pct" in result["summary"]
    assert result["summary"]["income"] == 4000