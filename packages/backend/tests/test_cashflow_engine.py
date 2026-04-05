"""Tests for cashflow engine (issue #70)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_forecast_length():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.cashflow_engine import daily_forecast
        result = daily_forecast(999, days_ahead=7)
        assert len(result["forecast"]) == 7

def test_forecast_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.cashflow_engine import daily_forecast
        result = daily_forecast(999, days_ahead=3)
        for day in result["forecast"]:
            assert "date" in day
            assert "net" in day
            assert "cumulative" in day

def test_cumulative_accumulates():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.cashflow_engine import daily_forecast
        result = daily_forecast(999, days_ahead=5)
        nets = [d["net"] for d in result["forecast"]]
        assert result["forecast"][-1]["cumulative"] == round(sum(nets), 2)
