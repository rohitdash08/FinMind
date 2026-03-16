import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";

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
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Keyboard Shortcuts</DialogTitle>
          <DialogDescription>
            Use these shortcuts to navigate the app quickly.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {shortcuts.map((shortcut, index) => (
            <div key={index} className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{shortcut.description}</span>
              <div className="flex items-center gap-1">
                {shortcut.prefix && (
                  <>
                    <Badge variant="secondary" className="px-1.5 font-mono text-[10px]">
                      {shortcut.prefix.toUpperCase()}
                    </Badge>
                    <span className="text-xs text-muted-foreground">+</span>
                  </>
                )}
                <Badge variant="secondary" className="px-1.5 font-mono text-[10px]">
                  {shortcut.key.toUpperCase()}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
