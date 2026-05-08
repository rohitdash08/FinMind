import { Moon, Sun, Monitor } from 'lucide-react';
import { useTheme } from './ThemeProvider';
import { Button } from '@/components/ui/button';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const cycle = () => {
    const next = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light';
    setTheme(next);
  };

  const icon =
    theme === 'light' ? <Sun className="h-4 w-4" /> :
    theme === 'dark' ? <Moon className="h-4 w-4" /> :
    <Monitor className="h-4 w-4" />;

  const label =
    theme === 'light' ? 'Light mode' :
    theme === 'dark' ? 'Dark mode' :
    'System theme';

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={cycle}
      aria-label={label}
      title={label}
      className="h-9 w-9"
    >
      {icon}
    </Button>
  );
}
