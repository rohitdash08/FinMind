import { useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";

type Shortcut = {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  description: string;
  action: () => void;
};

export function useKeyboardShortcuts() {
  const navigate = useNavigate();

  const shortcuts: Shortcut[] = [
    { key: "d", ctrl: true, description: "Go to Dashboard", action: () => navigate("/dashboard") },
    { key: "e", ctrl: true, description: "Go to Expenses", action: () => navigate("/expenses") },
    { key: "b", ctrl: true, description: "Go to Bills", action: () => navigate("/bills") },
    { key: "a", ctrl: true, description: "Go to Analytics", action: () => navigate("/analytics") },
    { key: "r", ctrl: true, description: "Go to Reminders", action: () => navigate("/reminders") },
    { key: "n", ctrl: true, shift: true, description: "New Expense", action: () => navigate("/expenses?new=1") },
    { key: "/", ctrl: false, description: "Focus Search", action: () => document.querySelector<HTMLInputElement>("[data-search]")?.focus() },
    { key: "?", shift: true, description: "Show Shortcuts", action: () => window.dispatchEvent(new CustomEvent("show-shortcuts")) },
  ];

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Don't trigger in input fields
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
      return;
    }

    for (const shortcut of shortcuts) {
      const ctrlMatch = shortcut.ctrl ? (e.ctrlKey || e.metaKey) : !(e.ctrlKey || e.metaKey);
      const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey || shortcut.key === "?";
      const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase();

      if (keyMatch && ctrlMatch && shiftMatch) {
        e.preventDefault();
        shortcut.action();
        return;
      }
    }
  }, [navigate]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return shortcuts;
}

export function ShortcutsHelp({ shortcuts }: { shortcuts: Shortcut[] }) {
  return (
    <div className="grid gap-2 p-4">
      <h3 className="font-semibold text-lg">Keyboard Shortcuts</h3>
      {shortcuts.map((s) => (
        <div key={s.key + (s.ctrl ? "ctrl" : "") + (s.shift ? "shift" : "")} className="flex justify-between items-center py-1">
          <span className="text-sm text-muted-foreground">{s.description}</span>
          <kbd className="px-2 py-1 text-xs bg-muted rounded border">
            {s.ctrl && "Ctrl+"}
            {s.shift && "Shift+"}
            {s.key.toUpperCase()}
          </kbd>
        </div>
      ))}
    </div>
  );
}
