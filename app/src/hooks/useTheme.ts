import { useState, useEffect, useCallback } from 'react';

export type ThemeMode = 'light' | 'dark' | 'system';

export interface UseThemeReturn {
  /** Current persisted preference ('light' | 'dark' | 'system'). */
  theme: ThemeMode;
  /** Update the persisted preference and apply it immediately. */
  setTheme: (mode: ThemeMode) => void;
  /** Whether the effective (resolved) theme is dark right now. */
  isDark: boolean;
}

const STORAGE_KEY = 'finmind-theme';

function getSystemPrefersDark(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function resolveEffective(mode: ThemeMode): boolean {
  if (mode === 'system') return getSystemPrefersDark();
  return mode === 'dark';
}

function readStored(): ThemeMode {
  if (typeof window === 'undefined') return 'system';
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === 'light' || raw === 'dark' || raw === 'system') return raw;
  return 'system';
}

function applyToDOM(dark: boolean): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.toggle('dark', dark);
  root.setAttribute('data-theme', dark ? 'dark' : 'light');
}

/**
 * React hook for theme management with dark/light/system support.
 *
 * - Persists the user preference to `localStorage`.
 * - Applies a `dark` class + `data-theme` attribute on `<html>`.
 * - Reacts to OS-level colour-scheme changes when set to `system`.
 *
 * Accessibility: toggling themes via `data-theme` lets CSS custom-properties
 * drive contrast ratios, ensuring WCAG AA compliance when the design tokens
 * are configured correctly.
 */
export function useTheme(): UseThemeReturn {
  const [theme, setThemeState] = useState<ThemeMode>(readStored);
  const [isDark, setIsDark] = useState(() => resolveEffective(readStored()));

  const setTheme = useCallback((mode: ThemeMode) => {
    localStorage.setItem(STORAGE_KEY, mode);
    setThemeState(mode);
    const dark = resolveEffective(mode);
    setIsDark(dark);
    applyToDOM(dark);
  }, []);

  // Apply on mount
  useEffect(() => {
    applyToDOM(isDark);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for OS-level changes when mode is 'system'
  useEffect(() => {
    if (theme !== 'system') return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      setIsDark(e.matches);
      applyToDOM(e.matches);
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [theme]);

  return { theme, setTheme, isDark };
}
