import React from 'react';
import { render, screen } from '@testing-library/react';
import { ThemeToggle } from '@/components/ui/theme-toggle';

jest.mock('next-themes', () => ({
  useTheme: () => ({
    theme: 'dark',
    setTheme: jest.fn(),
    resolvedTheme: 'dark',
    systemTheme: 'dark',
  }),
}));

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

describe('Dark mode a11y', () => {
  it('theme toggle is accessible with aria-label', () => {
    render(<ThemeToggle />);
    const toggle = screen.getByRole('button');
    expect(toggle).toHaveAttribute('aria-label');
    expect(toggle.getAttribute('aria-label')).toMatch(/switch to/i);
  });
});
