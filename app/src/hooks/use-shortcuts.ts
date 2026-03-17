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
    { key: "1", handler: () => navigate("/dashboard"), description: "Go to Dashboard" },
    { key: "d", prefix: "g", handler: () => navigate("/dashboard"), description: "Go to Dashboard" },
    
    { key: "2", handler: () => navigate("/budgets"), description: "Go to Budgets" },
    { key: "b", prefix: "g", handler: () => navigate("/budgets"), description: "Go to Budgets" },
    
    { key: "3", handler: () => navigate("/bills"), description: "Go to Bills" },
    { key: "l", prefix: "g", handler: () => navigate("/bills"), description: "Go to Bills" },
    
    { key: "4", handler: () => navigate("/reminders"), description: "Go to Reminders" },
    { key: "r", prefix: "g", handler: () => navigate("/reminders"), description: "Go to Reminders" },
    
    { key: "5", handler: () => navigate("/expenses"), description: "Go to Expenses" },
    { key: "e", prefix: "g", handler: () => navigate("/expenses"), description: "Go to Expenses" },
    
    { key: "6", handler: () => navigate("/analytics"), description: "Go to Analytics" },
    { key: "a", prefix: "g", handler: () => navigate("/analytics"), description: "Go to Analytics" },
    
    { key: "7", handler: () => navigate("/account"), description: "Go to Account" },
    { key: "c", prefix: "g", handler: () => navigate("/account"), description: "Go to Account" },

    { key: "q", prefix: "g", handler: () => window.dispatchEvent(new CustomEvent('fm_logout')), description: "Logout" },
    
    { key: "?", handler: () => setIsHelpOpen((prev) => !prev), description: "Show shortcuts" },
  ];

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const activeElement = document.activeElement;
      const isInput = activeElement?.tagName === "INPUT" || 
                      activeElement?.tagName === "TEXTAREA" || 
                      (activeElement as HTMLElement)?.isContentEditable;
      
      if (isInput) return;

      const key = event.key.toLowerCase();

      if (lastKeyRef.current === "g") {
        const shortcut = shortcuts.find(s => s.prefix === "g" && s.key === key);
        if (shortcut) {
          event.preventDefault();
          shortcut.handler();
          lastKeyRef.current = null;
          return;
        }
      }

      const singleKeyShortcut = shortcuts.find(s => !s.prefix && s.key === key);
      if (singleKeyShortcut) {
        event.preventDefault();
        singleKeyShortcut.handler();
        lastKeyRef.current = null;
        return;
      }

      if (key === "g") {
        lastKeyRef.current = "g";
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => {
          lastKeyRef.current = null;
        }, 1000);
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
