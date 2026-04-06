"""Dark mode & accessibility settings (issue #104)."""
import json, logging
from ..extensions import redis_client

logger = logging.getLogger("finmind.a11y")
PREFS_KEY = "a11y:prefs:{user_id}"
TTL = 60 * 60 * 24 * 365

THEMES = {
    "dark":  {"bg": "#0f0f0f", "surface": "#1a1a2e", "primary": "#7c3aed",
               "text": "#f8fafc", "muted": "#94a3b8", "border": "#334155"},
    "light": {"bg": "#ffffff", "surface": "#f8fafc", "primary": "#7c3aed",
               "text": "#0f172a", "muted": "#64748b", "border": "#e2e8f0"},
    "high_contrast": {"bg": "#000000", "surface": "#0a0a0a", "primary": "#ffffff",
                       "text": "#ffffff", "muted": "#cccccc", "border": "#ffffff"},
    "solarized": {"bg": "#002b36", "surface": "#073642", "primary": "#268bd2",
                   "text": "#839496", "muted": "#586e75", "border": "#657b83"},
}

FONT_SIZES = {"small": 13, "medium": 16, "large": 19, "xlarge": 22}


def get_preferences(user_id: int) -> dict:
    raw = redis_client.get(PREFS_KEY.format(user_id=user_id))
    if raw: return json.loads(raw)
    return {"theme": "dark", "font_size": "medium", "reduce_motion": False,
            "high_contrast": False, "focus_indicators": True, "dense_mode": False}


def set_preferences(user_id: int, prefs: dict) -> dict:
    current = get_preferences(user_id)
    current.update({k: v for k, v in prefs.items() if k in current})
    redis_client.setex(PREFS_KEY.format(user_id=user_id), TTL, json.dumps(current))
    return current


def get_theme_tokens(user_id: int) -> dict:
    prefs = get_preferences(user_id)
    theme_name = "high_contrast" if prefs.get("high_contrast") else prefs.get("theme", "dark")
    theme = THEMES.get(theme_name, THEMES["dark"])
    return {"theme": theme_name, "tokens": theme,
            "font_size_px": FONT_SIZES.get(prefs.get("font_size","medium"), 16),
            "reduce_motion": prefs.get("reduce_motion", False)}


def get_wcag_contrast_ratio(color1: str, color2: str) -> float:
    def luminance(hex_color):
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
        def adj(c): return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
        return 0.2126*adj(r) + 0.7152*adj(g) + 0.0722*adj(b)
    l1, l2 = luminance(color1), luminance(color2)
    if l1 < l2: l1, l2 = l2, l1
    return round((l1 + 0.05) / (l2 + 0.05), 2)
