import { useEffect, useCallback } from 'react';
import { ShortcutConfig, DEFAULT_SHORTCUTS } from '../api/shortcuts';

export type ShortcutHandler = (action: string) => void;

export function useKeyboardShortcuts(onAction: ShortcutHandler) {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      for (const shortcut of DEFAULT_SHORTCUTS) {
        const ctrlMatch = shortcut.ctrlKey
          ? event.ctrlKey || event.metaKey
          : true;
        const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase();

        if (ctrlMatch && keyMatch && (shortcut.ctrlKey === (event.ctrlKey || event.metaKey))) {
          event.preventDefault();
          onAction(shortcut.action);
          return;
        }
      }
    },
    [onAction],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);

  return DEFAULT_SHORTCUTS;
}
