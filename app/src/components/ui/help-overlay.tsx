import { useShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { Button } from '@/components/ui/button';
import { Keyboard, X } from 'lucide-react';
import { useEffect } from 'react';

export function HelpOverlay() {
  const { helpVisible, hideHelp, keybindings } = useShortcuts();

  useEffect(() => {
    function onEscape(e: KeyboardEvent) {
      if (e.key === 'Escape' && helpVisible) {
        hideHelp();
      }
    }
    window.addEventListener('keydown', onEscape);
    return () => window.removeEventListener('keydown', onEscape);
  }, [helpVisible, hideHelp]);

  if (!helpVisible) return null;

  const categories = [...new Set(keybindings.map((k) => k.category))];

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={hideHelp}
    >
      <div
        className="bg-white dark:bg-card rounded-2xl shadow-xl border max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <Keyboard className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-bold">Keyboard Shortcuts</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={hideHelp}>
            <X className="w-4 h-4" />
          </Button>
        </div>
        <div className="p-4 space-y-4">
          {categories.map((cat) => (
            <div key={cat}>
              <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">
                {cat}
              </h3>
              <div className="space-y-1.5">
                {keybindings
                  .filter((k) => k.category === cat)
                  .map((kb) => (
                    <div
                      key={kb.id}
                      className="flex items-center justify-between py-1.5"
                    >
                      <span className="text-sm">{kb.label}</span>
                      <kbd className="inline-flex items-center gap-0.5 rounded-md border bg-muted px-2 py-0.5 text-xs font-mono font-medium">
                        {kb.keys.split('+').map((part, i) => (
                          <span key={i}>
                            {i > 0 && <span className="mx-0.5">+</span>}
                            <span className="px-1 py-0.5 rounded bg-background border">
                              {part === '?' ? '?' : part.toUpperCase()}
                            </span>
                          </span>
                        ))}
                      </kbd>
                    </div>
                  ))}
              </div>
            </div>
          ))}
          <div className="pt-2 text-xs text-muted-foreground border-t">
            Press <kbd className="px-1 py-0.5 rounded border bg-muted font-mono">?</kbd> to toggle this overlay.
            Input fields are excluded from shortcuts.
          </div>
        </div>
      </div>
    </div>
  );
}
