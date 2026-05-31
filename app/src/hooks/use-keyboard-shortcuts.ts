import { useEffect, useCallback, useState } from 'react';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ShortcutAction =
  | 'navigate_dashboard'
  | 'navigate_budgets'
  | 'navigate_bills'
  | 'navigate_expenses'
  | 'navigate_analytics'
  | 'navigate_reminders'
  | 'navigate_search'
  | 'navigate_review'
  | 'navigate_account'
  | 'show_help'
  | 'search_focus'
  | 'new_transaction';

export type Keybinding = {
  id: ShortcutAction;
  label: string;
  keys: string;
  category: 'navigation' | 'actions' | 'general';
};

const DEFAULT_KEYBINDINGS: Keybinding[] = [
  { id: 'navigate_dashboard', label: 'Go to Dashboard', keys: 'g+d', category: 'navigation' },
  { id: 'navigate_budgets', label: 'Go to Budgets', keys: 'g+b', category: 'navigation' },
  { id: 'navigate_bills', label: 'Go to Bills', keys: 'g+i', category: 'navigation' },
  { id: 'navigate_expenses', label: 'Go to Expenses', keys: 'g+e', category: 'navigation' },
  { id: 'navigate_analytics', label: 'Go to Analytics', keys: 'g+a', category: 'navigation' },
  { id: 'navigate_reminders', label: 'Go to Reminders', keys: 'g+r', category: 'navigation' },
  { id: 'navigate_search', label: 'Go to Search', keys: 'g+s', category: 'navigation' },
  { id: 'navigate_review', label: 'Go to Review', keys: 'g+v', category: 'navigation' },
  { id: 'navigate_account', label: 'Go to Account', keys: 'g+u', category: 'navigation' },
  { id: 'show_help', label: 'Show Keyboard Shortcuts', keys: '?', category: 'general' },
  { id: 'search_focus', label: 'Focus Search', keys: '/', category: 'general' },
  { id: 'new_transaction', label: 'New Transaction', keys: 'n', category: 'actions' },
];

type ShortcutsState = {
  keybindings: Keybinding[];
  helpVisible: boolean;
  showHelp: () => void;
  hideHelp: () => void;
  toggleHelp: () => void;
  updateKeybinding: (id: ShortcutAction, keys: string) => void;
  resetDefaults: () => void;
};

export const useShortcuts = create<ShortcutsState>()(
  persist(
    (set) => ({
      keybindings: DEFAULT_KEYBINDINGS,
      helpVisible: false,
      showHelp: () => set({ helpVisible: true }),
      hideHelp: () => set({ helpVisible: false }),
      toggleHelp: () => set((s) => ({ helpVisible: !s.helpVisible })),
      updateKeybinding: (id, keys) =>
        set((state) => ({
          keybindings: state.keybindings.map((k) =>
            k.id === id ? { ...k, keys } : k,
          ),
        })),
      resetDefaults: () => set({ keybindings: DEFAULT_KEYBINDINGS }),
    }),
    { name: 'finmind-keybindings' },
  ),
);

type HandlerMap = Record<ShortcutAction, () => void>;

export function useKeyboardShortcuts(handlers: Partial<HandlerMap>) {
  const { keybindings, toggleHelp } = useShortcuts();
  const [buffer, setBuffer] = useState('');

  const matchSequence = useCallback(
    (seq: string) => {
      return keybindings.find((kb) => kb.keys === seq);
    },
    [keybindings],
  );

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        if (e.key === 'Escape') {
          (e.target as HTMLElement).blur();
        }
        return;
      }

      const key = e.key === '?' ? '?' : e.key.toLowerCase();

      if (key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        toggleHelp();
        return;
      }

      if (key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const handler = handlers['search_focus'];
        handler?.();
        return;
      }

      if (key === 'n' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const handler = handlers['new_transaction'];
        handler?.();
        return;
      }

      if (key === 'Escape') {
        const handler = handlers['show_help'];
        handler?.();
        return;
      }

      if (!e.ctrlKey && !e.metaKey && !e.altKey && key.length === 1) {
        const newBuf = (buffer + key).slice(-4);
        setBuffer(newBuf);

        const match = matchSequence(newBuf);
        if (match) {
          e.preventDefault();
          setBuffer('');
          const handler = handlers[match.id];
          handler?.();
          return;
        }

        const prefixMatch = keybindings.some(
          (kb) => kb.keys.startsWith(newBuf) && kb.keys !== newBuf,
        );
        if (!prefixMatch) {
          setBuffer('');
        }
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [buffer, keybindings, handlers, matchSequence, toggleHelp]);
}
