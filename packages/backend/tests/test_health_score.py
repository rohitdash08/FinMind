"""Tests for financial health score (issue #90)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_score_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.health_score import calculate_health_score
        result = calculate_health_score(999, 2026, 4)
        assert "score" in result
        assert "grade" in result
        assert "breakdown" in result
        assert result["grade"] in ("A","B","C","D","F")

def test_zero_income_low_score():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.health_score import calculate_health_score
        result = calculate_health_score(999, 2026, 4)
        assert result["score"] < 50  # no income = low score

def test_grade_boundaries():
    from app.services.health_score import _message
    assert "Excellent" in _message(85, "A")
    assert "Critical" in _message(20, "F")
