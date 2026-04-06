from unittest.mock import MagicMock, patch

def _mock_redis():
    store = {}
    r = MagicMock()
    def setex(k,t,v): store[k]=v
    def get(k): v=store.get(k); return v.encode() if isinstance(v,str) else v
    r.setex.side_effect=setex; r.get.side_effect=get
    return r

def test_default_prefs():
    with patch("app.services.accessibility.redis_client", _mock_redis()):
        from app.services.accessibility import get_preferences
        p = get_preferences(999)
        assert p["theme"] == "dark" and "font_size" in p

def test_set_preferences():
    r = _mock_redis()
    with patch("app.services.accessibility.redis_client", r):
        from app.services.accessibility import set_preferences, get_preferences
        set_preferences(1, {"theme": "light", "font_size": "large"})
        p = get_preferences(1)
        assert p["theme"] == "light" and p["font_size"] == "large"

def test_theme_tokens():
    with patch("app.services.accessibility.redis_client", _mock_redis()):
        from app.services.accessibility import get_theme_tokens
        t = get_theme_tokens(999)
        assert "tokens" in t and "font_size_px" in t

def test_wcag_contrast():
    from app.services.accessibility import get_wcag_contrast_ratio
    ratio = get_wcag_contrast_ratio("#ffffff", "#000000")
    assert ratio == 21.0  # max contrast
