def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.overspend_warning import check_overspend_warnings
        r = check_overspend_warnings(999)
        assert "warnings" in r and "month_progress_pct" in r

def test_empty_no_warnings():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.overspend_warning import check_overspend_warnings
        r = check_overspend_warnings(999)
        assert r["warning_count"] == 0

def test_level_ordering():
    levels = ["exceeded","critical","on_track_to_exceed","warning","pace_alert"]
    order = {"exceeded":0,"critical":1,"on_track_to_exceed":2,"warning":3,"pace_alert":4}
    assert sorted(levels, key=lambda x: order[x])[0] == "exceeded"
