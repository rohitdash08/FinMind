/**
 * Keyboard-first navigation & shortcuts hook.
 *
 * Provides global keyboard shortcuts for power-user navigation.
 * All shortcuts use modifier keys (Ctrl/Cmd) to avoid conflicts
 * with regular typing.
 *
 * Shortcuts:
 *   Ctrl/Cmd + D → Dashboard
 *   Ctrl/Cmd + E → Expenses
 *   Ctrl/Cmd + B → Bills
 *   Ctrl/Cmd + R → Reminders
 *   Ctrl/Cmd + A → Analytics
 *   Ctrl/Cmd + K → Focus search (if available)
 *   Ctrl/Cmd + N → New expense
 *   Escape       → Close modals / clear focus
 *   ?            → Show shortcut help (when not in an input)
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

export interface ShortcutConfig {
  key: string;
  ctrl?: boolean;
  description: string;
  action: () => void;
}

interface UseKeyboardShortcutsReturn {
  showHelp: boolean;
  setShowHelp: (show: boolean) => void;
  shortcuts: ShortcutConfig[];
}

export function useKeyboardShortcuts(): UseKeyboardShortcutsReturn {
  const navigate = useNavigate();
  const [showHelp, setShowHelp] = useState(false);

  const shortcuts: ShortcutConfig[] = [
    { key: "d", ctrl: true, description: "Go to Dashboard", action: () => navigate("/dashboard") },
    { key: "e", ctrl: true, description: "Go to Expenses", action: () => navigate("/expenses") },
    { key: "b", ctrl: true, description: "Go to Bills", action: () => navigate("/bills") },
    { key: "r", ctrl: true, description: "Go to Reminders", action: () => navigate("/reminders") },
    { key: "a", ctrl: true, description: "Go to Analytics", action: () => navigate("/analytics") },
    {
      key: "k",
      ctrl: true,
      description: "Focus search",
      action: () => {
        const searchInput = document.querySelector<HTMLInputElement>(
          'input[type="search"], input[placeholder*="search" i], input[placeholder*="Search" i]'
        );
        searchInput?.focus();
      },
    },
    {
      key: "n",
      ctrl: true,
      description: "New expense",
      action: () => {
        navigate("/expenses");
        // Trigger the add expense button after navigation
        setTimeout(() => {
          const addBtn = document.querySelector<HTMLButtonElement>(
            'button[aria-label*="add" i], button[aria-label*="new" i], button[data-action="add-expense"]'
          );
          addBtn?.click();
        }, 100);
      },
    },
    {
      key: "Escape",
      ctrl: false,
      description: "Close modal / clear focus",
      action: () => {
        setShowHelp(false);
        const active = document.activeElement as HTMLElement;
        active?.blur();
      },
    },
  ];

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      // Don't intercept shortcuts when typing in inputs
      const tag = (event.target as HTMLElement)?.tagName?.toLowerCase();
      const isInput = tag === "input" || tag === "textarea" || tag === "select";
      const isEditable = (event.target as HTMLElement)?.isContentEditable;

      // Show help on ? when not in an input
      if (event.key === "?" && !isInput && !isEditable && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        setShowHelp((prev) => !prev);
        return;
      }

      // Handle Escape even in inputs
      if (event.key === "Escape") {
        setShowHelp(false);
        const active = document.activeElement as HTMLElement;
        active?.blur();
        return;
      }

      // Ctrl/Cmd shortcuts
      const modifier = event.ctrlKey || event.metaKey;
      if (!modifier) return;

      const shortcut = shortcuts.find(
        (s) => s.ctrl && s.key.toLowerCase() === event.key.toLowerCase()
      );

      if (shortcut) {
        event.preventDefault();
        shortcut.action();
      }
    },
    [shortcuts]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return { showHelp, setShowHelp, shortcuts };
}
