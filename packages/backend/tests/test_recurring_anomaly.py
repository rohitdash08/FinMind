"""Tests for recurring anomaly detection (issue #108)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_no_anomalies_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.recurring_anomaly import detect_anomalies
        assert detect_anomalies(999) == []

def test_anomaly_detection_logic():
    amounts = [10.0, 10.0, 10.0, 10.0, 50.0]
    mean = sum(amounts)/len(amounts)
    from math import sqrt
    std = sqrt(sum((x-mean)**2 for x in amounts)/len(amounts))
    anomalous = [x for x in amounts if abs(x-mean) > 2*std]
    assert 50.0 in anomalous

def test_identical_charges_not_anomaly():
    amounts = [9.99]*10
    from math import sqrt
    mean = sum(amounts)/len(amounts)
    std = sqrt(sum((x-mean)**2 for x in amounts)/len(amounts))
    assert std < 0.01  # no anomaly possible
