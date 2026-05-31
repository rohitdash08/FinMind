import { useTheme as useNextTheme } from 'next-themes';
import { useEffect, useState } from 'react';

export function useTheme() {
  const { theme, setTheme, resolvedTheme, systemTheme } = useNextTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const effectiveTheme = mounted ? (resolvedTheme || 'light') : 'light';

  return {
    theme: mounted ? (theme || 'system') : 'system',
    effectiveTheme,
    systemTheme: mounted ? (systemTheme || 'light') : 'light',
    setTheme,
    isDark: effectiveTheme === 'dark',
    mounted,
  };
}
