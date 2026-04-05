"""Tests for spending heatmap (issue #116)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_heatmap_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.heatmap import get_heatmap
        result = get_heatmap(999, 2026, 4)
        assert "matrix" in result
        assert len(result["matrix"]) == 5
        assert len(result["matrix"][0]) == 7
        assert len(result["days"]) == 7

def test_heatmap_zero_state():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.heatmap import get_heatmap
        result = get_heatmap(999, 2026, 4)
        assert result["total"] == 0
        assert result["max_value"] == 0

def test_days_label():
    from app.services.heatmap import DAYS
    assert DAYS[0] == "Mon"
    assert DAYS[6] == "Sun"
    assert len(DAYS) == 7

def test_daily_list_has_correct_month():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.heatmap import get_heatmap
        result = get_heatmap(999, 2026, 4)
        for d in result["daily"]:
            assert d["date"].startswith("2026-04")
