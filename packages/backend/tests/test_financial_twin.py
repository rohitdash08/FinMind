def _app():
    from app import create_app
    return create_app({"TESTING":True,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:"})

def test_simulate_structure():
    app=_app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.financial_twin import simulate_scenario
        r=simulate_scenario(999,{"name":"Test","changes":[],"months_ahead":3})
        assert len(r["projections"])==3 and "baseline" in r

def test_income_increase():
    app=_app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.financial_twin import simulate_scenario
        r=simulate_scenario(999,{"changes":[{"type":"income_increase","monthly_amount":1000}],"months_ahead":6})
        assert r["simulated"]["monthly_income"]>=r["baseline"]["monthly_income"]

def test_verdict_field():
    app=_app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.financial_twin import simulate_scenario
        r=simulate_scenario(999,{"changes":[],"months_ahead":1})
        assert r["verdict"] in ("positive","negative")
