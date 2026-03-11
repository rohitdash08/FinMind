import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ThemeProvider, useTheme } from '@/hooks/use-theme';

const STORAGE_KEY = 'finmind-ui-theme';

function ThemeDisplay() {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={() => setTheme('dark')}>Set Dark</button>
      <button onClick={() => setTheme('light')}>Set Light</button>
      <button onClick={() => setTheme('system')}>Set System</button>
    </div>
  );
}

const renderWithProvider = (defaultTheme?: 'dark' | 'light' | 'system') =>
  render(
    <ThemeProvider defaultTheme={defaultTheme ?? 'system'} storageKey={STORAGE_KEY}>
      <ThemeDisplay />
    </ThemeProvider>
  );

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark', 'light');
  });

  it('defaults to system when no stored value', () => {
    renderWithProvider();
    expect(screen.getByTestId('theme').textContent).toBe('system');
  });

  it('reads persisted theme from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'dark');
    renderWithProvider();
    expect(screen.getByTestId('theme').textContent).toBe('dark');
  });

  it('applies dark class to documentElement when theme is dark', () => {
    renderWithProvider('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('light')).toBe(false);
  });

  it('applies light class to documentElement when theme is light', () => {
    renderWithProvider('light');
    expect(document.documentElement.classList.contains('light')).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('persists theme change to localStorage', () => {
    renderWithProvider();
    act(() => {
      fireEvent.click(screen.getByText('Set Dark'));
    });
    expect(localStorage.getItem(STORAGE_KEY)).toBe('dark');
    expect(screen.getByTestId('theme').textContent).toBe('dark');
  });

  it('switches from dark to light and updates class', () => {
    renderWithProvider('dark');
    act(() => {
      fireEvent.click(screen.getByText('Set Light'));
    });
    expect(document.documentElement.classList.contains('light')).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('returns a stable setTheme function across renders', () => {
    const { rerender } = renderWithProvider('light');
    const firstRender = screen.getByText('Set Dark');
    rerender(
      <ThemeProvider defaultTheme="light" storageKey={STORAGE_KEY}>
        <ThemeDisplay />
      </ThemeProvider>
    );
    expect(screen.getByText('Set Dark')).toBe(firstRender);
  });

  it('ignores invalid localStorage values and falls back to defaultTheme', () => {
    localStorage.setItem(STORAGE_KEY, 'foobar');
    renderWithProvider('light');
    expect(screen.getByTestId('theme').textContent).toBe('light');
    expect(document.documentElement.classList.contains('light')).toBe(true);
  });

  it('ignores empty string in localStorage and falls back to defaultTheme', () => {
    localStorage.setItem(STORAGE_KEY, '');
    renderWithProvider('dark');
    expect(screen.getByTestId('theme').textContent).toBe('dark');
  });

  it('responds to system prefers-color-scheme change when theme is system', () => {
    let changeHandler: (() => void) | null = null;
    const mockMq = {
      matches: false,
      addEventListener: jest.fn((_event: string, handler: () => void) => {
        changeHandler = handler;
      }),
      removeEventListener: jest.fn(),
    };
    jest.spyOn(window, 'matchMedia').mockReturnValue(mockMq as unknown as MediaQueryList);

    renderWithProvider('system');

    act(() => {
      mockMq.matches = true;
      if (changeHandler) changeHandler();
    });

    expect(document.documentElement.classList.contains('dark')).toBe(true);

    (window.matchMedia as jest.Mock).mockRestore?.();
  });

  it('throws when used outside ThemeProvider', () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<ThemeDisplay />)).toThrow('useTheme must be used within a ThemeProvider');
    consoleError.mockRestore();
  });
});
