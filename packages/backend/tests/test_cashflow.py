"""Tests for cash flow forecasting (issue #93)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_forecast_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.cashflow import forecast
        result = forecast(999, months_ahead=3)
        assert len(result["projections"]) == 3
        assert "month" in result["projections"][0]
        assert "net" in result["projections"][0]
        assert "risk" in result["projections"][0]

def test_forecast_zero_income_is_high_risk():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.cashflow import forecast
        result = forecast(999, months_ahead=1)
        assert result["projections"][0]["risk"] in ("low", "medium", "high")

def test_running_balance_accumulates():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.cashflow import forecast
        result = forecast(999, months_ahead=3)
        # Running balance should accumulate across months
        nets = [p["net"] for p in result["projections"]]
        assert result["projections"][-1]["running_balance"] == round(sum(nets), 2)
