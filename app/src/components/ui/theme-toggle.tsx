import { Moon, Sun, Monitor } from 'lucide-react';
import { useTheme } from '@/hooks/use-theme';
import { Button } from '@/components/ui/button';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const themes = [
    { value: 'light' as const, icon: Sun, label: 'Light mode' },
    { value: 'dark' as const, icon: Moon, label: 'Dark mode' },
    { value: 'system' as const, icon: Monitor, label: 'System preference' },
  ];

  const currentIndex = themes.findIndex((t) => t.value === theme);
  const nextIndex = (currentIndex + 1) % themes.length;
  const next = themes[nextIndex];

  return (
    <Button
      variant="outline"
      size="icon"
      className="h-9 w-9 rounded-full"
      onClick={() => setTheme(next.value)}
      aria-label={`Switch to ${next.label}`}
    >
      {themes.map((t) => {
        const Icon = t.icon;
        return (
          <Icon
            key={t.value}
            className={`h-4 w-4 transition-all ${
              t.value === theme ? 'scale-100 opacity-100' : 'scale-0 opacity-0 absolute'
            }`}
          />
        );
      })}
    </Button>
  );
}
