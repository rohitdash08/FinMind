def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_onboarding_status_new_user():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.onboarding import get_onboarding_status
        r = get_onboarding_status(999)
        assert r["completed"] == 0 and not r["complete"]

def test_setup_default_categories():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.onboarding import setup_default_categories
        assert len(setup_default_categories(1)) == 12

def test_invalid_preset_raises():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.onboarding import apply_budget_preset
        import pytest
        with pytest.raises(ValueError): apply_budget_preset(1, "bad")
