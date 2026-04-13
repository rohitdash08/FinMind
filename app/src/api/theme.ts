/**
 * TypeScript types for theme configuration.
 *
 * These types describe the shape of theme-related data used across
 * the frontend. They are intentionally kept separate from the React
 * hook so that non-React utilities (e.g. Storybook, tests, SSR) can
 * import them without pulling in React.
 */

/** Supported theme modes. */
export type ThemeMode = 'light' | 'dark' | 'system';

/** A single design-token value that varies by theme. */
export interface ThemeToken {
  light: string;
  dark: string;
}

/** Palette subset used for accessibility contrast checks. */
export interface ThemePalette {
  background: ThemeToken;
  foreground: ThemeToken;
  primary: ThemeToken;
  primaryForeground: ThemeToken;
  muted: ThemeToken;
  mutedForeground: ThemeToken;
  border: ThemeToken;
}

/** Full theme configuration object. */
export interface ThemeConfig {
  /** Display name shown in the settings UI. */
  name: string;
  /** Which mode this config represents. */
  mode: ThemeMode;
  /** Core colour palette. */
  palette: ThemePalette;
  /** Minimum contrast ratio target (WCAG AA = 4.5, AAA = 7). */
  contrastTarget: number;
}

/** Persisted user preference stored in localStorage. */
export interface ThemePreference {
  mode: ThemeMode;
  /** ISO-8601 timestamp of last change. */
  updatedAt: string;
}
