import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { useMemo } from "react";

type Shortcut = {
  key: string;
  prefix?: string;
  description: string;
};

interface ShortcutHelpModalProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  shortcuts: Shortcut[];
}

export function ShortcutHelpModal({ isOpen, onOpenChange, shortcuts }: ShortcutHelpModalProps) {
  // Group shortcuts by description for a cleaner display
  const groupedShortcuts = useMemo(() => {
    const groups: Record<string, Shortcut[]> = {};
    shortcuts.forEach((s) => {
      if (!groups[s.description]) {
        groups[s.description] = [];
      }
      groups[s.description].push(s);
    });
    return Object.entries(groups);
  }, [shortcuts]);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle>Keyboard Shortcuts</DialogTitle>
          <DialogDescription>
            Use these shortcuts to navigate the app quickly.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {groupedShortcuts.map(([description, variants], index) => (
            <div key={index} className="flex items-center justify-between">
              <span className="text-sm font-medium text-foreground/90">{description}</span>
              <div className="flex items-center gap-2">
                {variants.map((v, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    {i > 0 && <span className="text-xs text-muted-foreground/60">or</span>}
                    <div className="flex items-center gap-1">
                      {v.prefix && (
                        <>
                          <Badge variant="outline" className="px-1.5 font-mono text-[11px] h-5 min-w-[22px] flex items-center justify-center">
                            {v.prefix.toUpperCase()}
                          </Badge>
                          <span className="text-xs text-muted-foreground">+</span>
                        </>
                      )}
                      {v.key === "?" ? (
                        <>
                          <Badge variant="outline" className="px-1.5 font-mono text-[11px] h-5 flex items-center justify-center">
                            SHIFT
                          </Badge>
                          <span className="text-xs text-muted-foreground">+</span>
                          <Badge variant="secondary" className="px-1.5 font-mono text-[11px] h-5 min-w-[22px] flex items-center justify-center">
                            ?
                          </Badge>
                        </>
                      ) : (
                        <Badge variant="secondary" className="px-1.5 font-mono text-[11px] h-5 min-w-[22px] flex items-center justify-center">
                          {v.key.toUpperCase()}
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
