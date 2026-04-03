import pytest
from datetime import datetime, timedelta
from app.services.anomaly_engine import AnomalyDetectionEngine, _transactions

@pytest.fixture(autouse=True)
def clear_data():
    _transactions.clear()
    yield
    _transactions.clear()

@pytest.fixture
def engine():
    return AnomalyDetectionEngine()

def add_txn(user_id, date_str, amount, category="food", txn_id=None):
    _transactions[user_id].append({
        "id": txn_id or f"txn-{len(_transactions[user_id])}",
        "date": date_str,
        "amount": amount,
        "category": category,
    })

def test_amount_outlier_detected(engine):
    """A large outlier transaction should be flagged."""
    now = datetime.utcnow()
    for i in range(10):
        dt = (now - timedelta(days=i+1)).isoformat()
        add_txn("u1", dt, 20 + i, "food")
    # Add huge outlier
    add_txn("u1", (now - timedelta(days=0, hours=1)).isoformat(), 5000, "food")
    anomalies = engine.detect_anomalies("u1")
    types = [a["anomaly_type"] for a in anomalies]
    assert "amount_outlier" in types

def test_duplicate_detected(engine):
    """Two identical transactions within 24h should be flagged."""
    now = datetime.utcnow()
    add_txn("u2", (now - timedelta(hours=2)).isoformat(), 100, "subscriptions", "txn-a")
    add_txn("u2", (now - timedelta(hours=1)).isoformat(), 100, "subscriptions", "txn-b")
    # Add baseline
    for i in range(5):
        add_txn("u2", (now - timedelta(days=i+2)).isoformat(), 30, "food")
    anomalies = engine.detect_anomalies("u2")
    types = [a["anomaly_type"] for a in anomalies]
    assert "potential_duplicate" in types

def test_no_anomaly_below_threshold(engine):
    """Normal transactions should not trigger anomalies."""
    now = datetime.utcnow()
    for i in range(20):
        dt = (now - timedelta(days=i)).isoformat()
        add_txn("u3", dt, 50, "food")
    anomalies = engine.detect_anomalies("u3")
    outliers = [a for a in anomalies if a["anomaly_type"] == "amount_outlier"]
    assert len(outliers) == 0

def test_few_transactions_return_empty(engine):
    """Less than 5 transactions should return no anomalies."""
    now = datetime.utcnow()
    for i in range(3):
        add_txn("u4", (now - timedelta(days=i)).isoformat(), 100, "food")
    anomalies = engine.detect_anomalies("u4")
    assert anomalies == []

def test_anomalies_sorted_by_score(engine):
    """Anomalies are returned sorted by score descending."""
    now = datetime.utcnow()
    for i in range(15):
        add_txn("u5", (now - timedelta(days=i+1)).isoformat(), 30, "food")
    add_txn("u5", (now - timedelta(hours=1)).isoformat(), 10000, "food")
    anomalies = engine.detect_anomalies("u5")
    if len(anomalies) > 1:
        scores = [a["score"] for a in anomalies]
        assert scores == sorted(scores, reverse=True)