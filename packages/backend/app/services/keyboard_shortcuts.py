"""Keyboard-first navigation & shortcuts registry (issue #106)."""

SHORTCUTS = {
    "global": [
        {"key": "g e", "action": "navigate_expenses", "description": "Go to Expenses"},
        {"key": "g b", "action": "navigate_budget", "description": "Go to Budget"},
        {"key": "g d", "action": "navigate_dashboard", "description": "Go to Dashboard"},
        {"key": "g r", "action": "navigate_reports", "description": "Go to Reports"},
        {"key": "g s", "action": "navigate_settings", "description": "Go to Settings"},
        {"key": "?", "action": "show_shortcuts", "description": "Show keyboard shortcuts"},
        {"key": "/", "action": "focus_search", "description": "Focus search"},
    ],
    "expenses": [
        {"key": "n", "action": "new_expense", "description": "New expense"},
        {"key": "e", "action": "edit_selected", "description": "Edit selected"},
        {"key": "d", "action": "delete_selected", "description": "Delete selected"},
        {"key": "f", "action": "filter", "description": "Open filters"},
        {"key": "x", "action": "export", "description": "Export expenses"},
        {"key": "j", "action": "select_next", "description": "Select next row"},
        {"key": "k", "action": "select_prev", "description": "Select previous row"},
        {"key": "Enter", "action": "open_selected", "description": "Open selected"},
        {"key": "Escape", "action": "clear_selection", "description": "Clear selection"},
    ],
    "forms": [
        {"key": "Ctrl+Enter", "action": "submit_form", "description": "Submit form"},
        {"key": "Escape", "action": "cancel_form", "description": "Cancel / close"},
        {"key": "Tab", "action": "next_field", "description": "Next field"},
        {"key": "Shift+Tab", "action": "prev_field", "description": "Previous field"},
    ],
    "dashboard": [
        {"key": "r", "action": "refresh", "description": "Refresh data"},
        {"key": "1-9", "action": "focus_widget", "description": "Focus widget 1-9"},
        {"key": "f", "action": "fullscreen_widget", "description": "Fullscreen current widget"},
    ],
}


def get_shortcuts(context: str = None) -> dict:
    if context and context in SHORTCUTS:
        return {"context": context, "shortcuts": SHORTCUTS[context]}
    return {"contexts": list(SHORTCUTS.keys()), "all": SHORTCUTS}


def find_shortcut(key: str) -> list:
    matches = []
    for context, shortcuts in SHORTCUTS.items():
        for s in shortcuts:
            if s["key"].lower() == key.lower():
                matches.append({**s, "context": context})
    return matches
