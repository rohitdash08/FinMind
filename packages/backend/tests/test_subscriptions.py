"""Tests for subscription detection (issues #109, #110)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_no_subscriptions_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.subscriptions import detect_subscriptions
        assert detect_subscriptions(999) == []

def test_subscription_patterns():
    from app.services.subscriptions import SUBSCRIPTION_PATTERNS
    import re
    assert any(re.search(p, "netflix", re.I) for p in SUBSCRIPTION_PATTERNS)
    assert any(re.search(p, "spotify premium", re.I) for p in SUBSCRIPTION_PATTERNS)

def test_cadences_defined():
    from app.services.subscriptions import CADENCES
    assert 30 in CADENCES  # monthly
    assert 7 in CADENCES   # weekly

def test_no_increases_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.subscriptions import detect_price_increases
        assert detect_price_increases(999) == []
