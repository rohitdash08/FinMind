"""Tests for essential vs discretionary breakdown (issue #120)."""

def test_classify_essential():
    from app.services.spending_breakdown import classify_category
    assert classify_category("groceries") == "essential"
    assert classify_category("Rent") == "essential"

def test_classify_discretionary():
    from app.services.spending_breakdown import classify_category
    assert classify_category("Netflix") == "discretionary"
    assert classify_category("Gaming") == "discretionary"

def test_user_override():
    from app.services.spending_breakdown import classify_category
    overrides = {"netflix": "essential"}
    assert classify_category("Netflix", overrides) == "essential"

def test_breakdown_zero_state():
    from app import create_app
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.spending_breakdown import get_spending_breakdown
        result = get_spending_breakdown(999, 2026, 4)
        assert result["total"] == 0
        assert result["essential"]["total"] == 0
        assert result["discretionary"]["total"] == 0

def test_insight_high_discretionary():
    from app.services.spending_breakdown import _insight
    msg = _insight(100, 400, 500)  # 80% discretionary
    assert "discretionary" in msg.lower()
