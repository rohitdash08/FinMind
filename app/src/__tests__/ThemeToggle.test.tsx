import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeToggle } from '@/components/ui/theme-toggle';

const setThemeMock = jest.fn();
jest.mock('next-themes', () => ({
  useTheme: () => ({
    theme: 'light',
    setTheme: setThemeMock,
    resolvedTheme: 'light',
    systemTheme: 'light',
  }),
}));

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

describe('ThemeToggle', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders theme toggle button', () => {
    render(<ThemeToggle />);
    const btn = screen.getByRole('button', { name: /switch to/i });
    expect(btn).toBeInTheDocument();
  });

  it('cycles through themes on click', () => {
    render(<ThemeToggle />);
    const btn = screen.getByRole('button', { name: /switch to/i });
    fireEvent.click(btn);
    expect(setThemeMock).toHaveBeenCalledWith('dark');
  });
});
