"""Tests for anomaly engine (issue #72)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_no_anomalies_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.anomaly_engine import detect_all_anomalies
        result = detect_all_anomalies(999, 2026, 4)
        assert result["anomaly_count"] == 0
        assert result["anomalies"] == []

def test_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.anomaly_engine import detect_all_anomalies
        result = detect_all_anomalies(999, 2026, 4)
        assert "period" in result
        assert "anomalies" in result
        assert "summary" in result

def test_large_transaction_logic():
    amounts = [10,10,10,10,10,10,500]  # 500 is 3σ+ outlier
    mean = sum(amounts)/len(amounts)
    std = (sum((x-mean)**2 for x in amounts)/len(amounts))**0.5
    outliers = [x for x in amounts if (x-mean) > 3*std]
    assert 500 in outliers
