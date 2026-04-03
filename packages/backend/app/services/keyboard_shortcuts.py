"""
Keyboard Navigation & Shortcuts (issue #106)

Backend service for managing user-configurable keyboard shortcuts.
Provides a registry of available shortcuts and user preferences.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from app.extensions import db


# -----------------------------------------------------------------------
# Default shortcut definitions (action -> default keybinding)
# -----------------------------------------------------------------------

DEFAULT_SHORTCUTS: dict[str, dict] = {
    # Navigation
    "nav.dashboard": {
        "action": "nav.dashboard",
        "label": "Go to Dashboard",
        "default_key": "g d",
        "category": "navigation",
        "description": "Navigate to the main dashboard",
    },
    "nav.expenses": {
        "action": "nav.expenses",
        "label": "Go to Expenses",
        "default_key": "g e",
        "category": "navigation",
        "description": "Navigate to expense list",
    },
    "nav.bills": {
        "action": "nav.bills",
        "label": "Go to Bills",
        "default_key": "g b",
        "category": "navigation",
        "description": "Navigate to bills",
    },
    "nav.insights": {
        "action": "nav.insights",
        "label": "Go to Insights",
        "default_key": "g i",
        "category": "navigation",
        "description": "Navigate to financial insights",
    },
    "nav.categories": {
        "action": "nav.categories",
        "label": "Go to Categories",
        "default_key": "g c",
        "category": "navigation",
        "description": "Navigate to category management",
    },
    # Actions
    "action.new_expense": {
        "action": "action.new_expense",
        "label": "New Expense",
        "default_key": "n e",
        "category": "actions",
        "description": "Open new expense dialog",
    },
    "action.new_bill": {
        "action": "action.new_bill",
        "label": "New Bill",
        "default_key": "n b",
        "category": "actions",
        "description": "Open new bill dialog",
    },
    "action.search": {
        "action": "action.search",
        "label": "Global Search",
        "default_key": "/",
        "category": "actions",
        "description": "Open global search",
    },
    "action.import": {
        "action": "action.import",
        "label": "Import Transactions",
        "default_key": "ctrl+i",
        "category": "actions",
        "description": "Open import dialog",
    },
    "action.export": {
        "action": "action.export",
        "label": "Export Data",
        "default_key": "ctrl+e",
        "category": "actions",
        "description": "Export user data",
    },
    # UI controls
    "ui.toggle_sidebar": {
        "action": "ui.toggle_sidebar",
        "label": "Toggle Sidebar",
        "default_key": "ctrl+\\",
        "category": "ui",
        "description": "Show/hide the sidebar",
    },
    "ui.toggle_dark_mode": {
        "action": "ui.toggle_dark_mode",
        "label": "Toggle Dark Mode",
        "default_key": "ctrl+shift+d",
        "category": "ui",
        "description": "Toggle dark/light theme",
    },
    "ui.help": {
        "action": "ui.help",
        "label": "Show Keyboard Help",
        "default_key": "?",
        "category": "ui",
        "description": "Show keyboard shortcuts reference",
    },
    "ui.close_modal": {
        "action": "ui.close_modal",
        "label": "Close Modal",
        "default_key": "Escape",
        "category": "ui",
        "description": "Close the current modal or dialog",
    },
    "ui.next_item": {
        "action": "ui.next_item",
        "label": "Next Item",
        "default_key": "j",
        "category": "ui",
        "description": "Move to next item in list (vim-style)",
    },
    "ui.prev_item": {
        "action": "ui.prev_item",
        "label": "Previous Item",
        "default_key": "k",
        "category": "ui",
        "description": "Move to previous item in list (vim-style)",
    },
}


class UserShortcutPreference(db.Model):
    """User-specific keyboard shortcut customizations."""

    __tablename__ = "user_shortcut_preferences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    custom_key = db.Column(db.String(50), nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "custom_key": self.custom_key,
            "enabled": self.enabled,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def get_all_shortcuts() -> list[dict]:
    """Return the full list of available shortcuts with metadata."""
    return list(DEFAULT_SHORTCUTS.values())


def get_shortcuts_by_category() -> dict[str, list[dict]]:
    """Group shortcuts by category."""
    result: dict[str, list] = {}
    for shortcut in DEFAULT_SHORTCUTS.values():
        cat = shortcut["category"]
        result.setdefault(cat, []).append(shortcut)
    return result


def get_user_shortcut_config(user_id: int) -> list[dict]:
    """
    Get resolved keyboard shortcuts for a user.
    Merges defaults with user customizations.
    """
    prefs = UserShortcutPreference.query.filter_by(user_id=user_id).all()
    pref_map = {p.action: p for p in prefs}

    result = []
    for action, shortcut in DEFAULT_SHORTCUTS.items():
        entry = dict(shortcut)
        if action in pref_map:
            pref = pref_map[action]
            entry["custom_key"] = pref.custom_key
            entry["enabled"] = pref.enabled
            entry["active_key"] = pref.custom_key if pref.enabled else None
            entry["is_customized"] = True
        else:
            entry["custom_key"] = None
            entry["enabled"] = True
            entry["active_key"] = shortcut["default_key"]
            entry["is_customized"] = False
        result.append(entry)
    return result


def update_shortcut(user_id: int, action: str, custom_key: str, enabled: bool = True) -> Optional[dict]:
    """
    Set a custom key binding for an action.
    Returns updated shortcut config or None if action doesn't exist.
    """
    if action not in DEFAULT_SHORTCUTS:
        return None

    # Check for conflicts with other custom bindings
    conflict = UserShortcutPreference.query.filter(
        UserShortcutPreference.user_id == user_id,
        UserShortcutPreference.custom_key == custom_key,
        UserShortcutPreference.action != action,
        UserShortcutPreference.enabled == True,
    ).first()
    if conflict:
        return {"error": f"Key '{custom_key}' is already assigned to '{conflict.action}'"}

    pref = UserShortcutPreference.query.filter_by(user_id=user_id, action=action).first()
    if pref:
        pref.custom_key = custom_key
        pref.enabled = enabled
    else:
        pref = UserShortcutPreference(
            user_id=user_id,
            action=action,
            custom_key=custom_key,
            enabled=enabled,
        )
        db.session.add(pref)
    db.session.commit()

    shortcut = dict(DEFAULT_SHORTCUTS[action])
    shortcut["custom_key"] = custom_key
    shortcut["enabled"] = enabled
    shortcut["active_key"] = custom_key if enabled else None
    shortcut["is_customized"] = True
    return shortcut


def reset_shortcut(user_id: int, action: str) -> Optional[dict]:
    """Reset a shortcut to its default key binding."""
    if action not in DEFAULT_SHORTCUTS:
        return None
    pref = UserShortcutPreference.query.filter_by(user_id=user_id, action=action).first()
    if pref:
        db.session.delete(pref)
        db.session.commit()
    return {**DEFAULT_SHORTCUTS[action], "is_customized": False, "active_key": DEFAULT_SHORTCUTS[action]["default_key"]}


def reset_all_shortcuts(user_id: int) -> int:
    """Reset all shortcuts for a user to defaults. Returns count deleted."""
    prefs = UserShortcutPreference.query.filter_by(user_id=user_id).all()
    count = len(prefs)
    for p in prefs:
        db.session.delete(p)
    db.session.commit()
    return count