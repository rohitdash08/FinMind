import pytest
from datetime import datetime
from app.services.spending_heatmap import SpendingHeatmapService, _transactions

@pytest.fixture(autouse=True)
def clear_data():
    _transactions.clear()
    yield
    _transactions.clear()

@pytest.fixture
def svc():
    return SpendingHeatmapService()

def add_txn(user_id, date_str, amount, category="food"):
    _transactions[user_id].append({"date": date_str, "amount": amount, "category": category})

def test_monthly_heatmap_empty(svc):
    """Empty heatmap for user with no transactions."""
    result = svc.monthly_heatmap("user_empty", year=2026, month=3)
    assert result["period"] == "month"
    assert result["summary"]["total_spending"] == 0
    assert len(result["cells"]) == 31  # March has 31 days

def test_monthly_heatmap_aggregation(svc):
    """Transactions are correctly aggregated by day."""
    add_txn("u1", "2026-04-01T10:00:00", 25.50)
    add_txn("u1", "2026-04-01T14:00:00", 10.00)
    add_txn("u1", "2026-04-03T09:00:00", 50.00)
    result = svc.monthly_heatmap("u1", year=2026, month=4)
    cells = {c["day"]: c for c in result["cells"]}
    assert cells[1]["amount"] == pytest.approx(35.50, rel=1e-3)
    assert cells[1]["count"] == 2
    assert cells[3]["amount"] == pytest.approx(50.00, rel=1e-3)
    assert result["summary"]["peak_day"] == 3

def test_monthly_heatmap_category_filter(svc):
    """Category filter limits which transactions are included."""
    add_txn("u2", "2026-04-05T10:00:00", 100.00, category="rent")
    add_txn("u2", "2026-04-05T12:00:00", 20.00, category="food")
    result = svc.monthly_heatmap("u2", year=2026, month=4, category="food")
    cells = {c["day"]: c for c in result["cells"]}
    assert cells[5]["amount"] == pytest.approx(20.00)

def test_yearly_heatmap_monthly_breakdown(svc):
    """Yearly heatmap groups by month."""
    add_txn("u3", "2026-01-10T00:00:00", 100.00, category="food")
    add_txn("u3", "2026-03-15T00:00:00", 200.00, category="rent")
    result = svc.yearly_heatmap("u3", year=2026)
    monthly = {m["month"]: m["amount"] for m in result["monthly_breakdown"]}
    assert monthly[1] == pytest.approx(100.00)
    assert monthly[3] == pytest.approx(200.00)
    assert result["summary"]["peak_month"] == 3

def test_peak_spending_summary(svc):
    """Peak spending summary identifies top days correctly."""
    add_txn("u4", "2026-04-10T00:00:00", 500.00)
    add_txn("u4", "2026-04-12T00:00:00", 50.00)
    summary = svc.peak_spending_summary("u4", year=2026, month=4)
    assert summary["top_spending_days"][0]["day"] == 10
    assert summary["top_spending_days"][0]["amount"] == pytest.approx(500.00)

def test_heatmap_cells_count(svc):
    """Monthly heatmap has correct number of cells per month."""
    result_feb = svc.monthly_heatmap("u5", year=2026, month=2)
    assert len(result_feb["cells"]) == 28  # 2026 is not a leap year
