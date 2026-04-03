/**
 * Keyboard shortcut help overlay.
 * Shown when user presses '?' and dismissed with Escape or clicking outside.
 */

import type { ShortcutConfig } from "../hooks/useKeyboardShortcuts";

interface Props {
  shortcuts: ShortcutConfig[];
  open: boolean;
  onClose: () => void;
}

export function KeyboardShortcutHelp({ shortcuts, open, onClose }: Props) {
  if (!open) return null;

  const isMac =
    typeof navigator !== "undefined" && /Mac|iPod|iPhone|iPad/.test(navigator.userAgent);
  const modKey = isMac ? "⌘" : "Ctrl";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-label="Keyboard shortcuts"
    >
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl p-6 max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            ⌨️ Keyboard Shortcuts
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="space-y-2">
          {shortcuts
            .filter((s) => s.key !== "Escape")
            .map((shortcut) => (
              <div
                key={shortcut.key}
                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  {shortcut.description}
                </span>
                <kbd className="inline-flex items-center gap-1 px-2 py-1 text-xs font-mono bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded border border-gray-200 dark:border-gray-700">
                  {shortcut.ctrl && <span>{modKey} +</span>}
                  <span className="uppercase">{shortcut.key}</span>
                </kbd>
              </div>
            ))}

          {/* Static entries */}
          <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800">
            <span className="text-sm text-gray-700 dark:text-gray-300">
              Close modal / clear focus
            </span>
            <kbd className="px-2 py-1 text-xs font-mono bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded border border-gray-200 dark:border-gray-700">
              Esc
            </kbd>
          </div>
          <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800">
            <span className="text-sm text-gray-700 dark:text-gray-300">
              Show this help
            </span>
            <kbd className="px-2 py-1 text-xs font-mono bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded border border-gray-200 dark:border-gray-700">
              ?
            </kbd>
          </div>
        </div>

        <p className="mt-4 text-xs text-gray-500 text-center">
          Press <kbd className="px-1 rounded bg-gray-100 dark:bg-gray-800">?</kbd> anywhere to
          toggle this panel
        </p>
      </div>
    </div>
  );
}
