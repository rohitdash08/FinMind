from app.services.keyboard_shortcuts import get_shortcuts, find_shortcut

def test_get_all_shortcuts():
    r = get_shortcuts()
    assert "contexts" in r and "all" in r
    assert "global" in r["contexts"]

def test_get_context_shortcuts():
    r = get_shortcuts("expenses")
    assert r["context"] == "expenses"
    assert any(s["action"] == "new_expense" for s in r["shortcuts"])

def test_find_shortcut():
    matches = find_shortcut("n")
    assert any(m["action"] == "new_expense" for m in matches)

def test_unknown_context():
    r = get_shortcuts("nonexistent")
    assert "contexts" in r
