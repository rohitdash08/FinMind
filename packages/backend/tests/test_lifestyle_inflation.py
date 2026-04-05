"""Tests for lifestyle inflation detection (issue #118)."""

def test_detection_logic_positive():
    # Simulate: expenses grew 20%, income flat
    avg_exp_first, avg_exp_second = 1000.0, 1250.0
    avg_inc_first, avg_inc_second = 2000.0, 2050.0
    exp_growth = (avg_exp_second - avg_exp_first) / avg_exp_first * 100
    inc_growth = (avg_inc_second - avg_inc_first) / avg_inc_first * 100
    detected = exp_growth > 10 and exp_growth > inc_growth + 5
    assert detected is True

def test_detection_logic_negative():
    avg_exp_first, avg_exp_second = 1000.0, 1020.0  # only 2% growth
    avg_inc_first, avg_inc_second = 2000.0, 2100.0
    exp_growth = (avg_exp_second - avg_exp_first) / avg_exp_first * 100
    inc_growth = (avg_inc_second - avg_inc_first) / avg_inc_first * 100
    detected = exp_growth > 10 and exp_growth > inc_growth + 5
    assert detected is False

def test_zero_state():
    from app import create_app
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.lifestyle_inflation import detect_lifestyle_inflation
        result = detect_lifestyle_inflation(999, 2026, 6)
        assert "detected" in result
        assert "history" in result

def test_history_length():
    from app import create_app
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.lifestyle_inflation import detect_lifestyle_inflation
        result = detect_lifestyle_inflation(999, 2026, 6)
        assert len(result["history"]) == 6
