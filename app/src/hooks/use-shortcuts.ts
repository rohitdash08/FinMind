import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

type ShortcutHandler = {
  key: string;
  prefix?: string;
  handler: () => void;
  description: string;
};

export function useShortcuts() {
  const navigate = useNavigate();
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const lastKeyRef = useRef<string | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const shortcuts: ShortcutHandler[] = [
    { key: "d", prefix: "g", handler: () => navigate("/dashboard"), description: "Go to Dashboard" },
    { key: "e", prefix: "g", handler: () => navigate("/expenses"), description: "Go to Expenses" },
    { key: "b", prefix: "g", handler: () => navigate("/bills"), description: "Go to Bills" },
    { key: "r", prefix: "g", handler: () => navigate("/reminders"), description: "Go to Reminders" },
    { key: "a", prefix: "g", handler: () => navigate("/analytics"), description: "Go to Analytics" },
    { key: "?", handler: () => setIsHelpOpen(true), description: "Show keyboard shortcuts" },
  ];

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Ignore if typing in an input/textarea
      const activeElement = document.activeElement;
      const isInput = activeElement?.tagName === "INPUT" || 
                      activeElement?.tagName === "TEXTAREA" || 
                      (activeElement as HTMLElement)?.isContentEditable;
      
      if (isInput) return;

      const key = event.key.toLowerCase();

      // Handle "G" prefix shortcuts
      if (lastKeyRef.current === "g") {
        const shortcut = shortcuts.find(s => s.prefix === "g" && s.key === key);
        if (shortcut) {
          event.preventDefault();
          shortcut.handler();
          lastKeyRef.current = null;
          return;
        }
      }

      // Handle single key shortcuts
      const singleKeyShortcut = shortcuts.find(s => !s.prefix && s.key === key);
      if (singleKeyShortcut) {
        event.preventDefault();
        singleKeyShortcut.handler();
        lastKeyRef.current = null;
        return;
      }

      // Set prefix
      if (key === "g") {
        lastKeyRef.current = "g";
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => {
          lastKeyRef.current = null;
        }, 1000); // 1 second window
      } else {
        lastKeyRef.current = null;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [navigate]);

  return { isHelpOpen, setIsHelpOpen, shortcuts };
}
