import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { HelpOverlay } from '@/components/ui/help-overlay';

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

describe('Keyboard shortcuts store', () => {
  afterEach(() => {
    cleanup();
    useShortcuts.getState().hideHelp();
  });

  it('starts with default keybindings', () => {
    const state = useShortcuts.getState();
    expect(state.keybindings.length).toBeGreaterThan(0);
    expect(state.keybindings.some((b) => b.id === 'navigate_dashboard')).toBe(true);
    expect(state.keybindings.some((b) => b.id === 'show_help')).toBe(true);
  });

  it('can show and hide help', () => {
    const s = useShortcuts.getState();
    s.showHelp();
    expect(useShortcuts.getState().helpVisible).toBe(true);
    s.hideHelp();
    expect(useShortcuts.getState().helpVisible).toBe(false);
  });
});

describe('HelpOverlay', () => {
  afterEach(() => {
    cleanup();
    useShortcuts.getState().hideHelp();
  });

  it('renders nothing when help is hidden', () => {
    useShortcuts.getState().hideHelp();
    const { container } = render(<HelpOverlay />);
    expect(container.innerHTML).toBe('');
  });

  it('renders shortcuts when help is visible', () => {
    useShortcuts.getState().showHelp();
    render(<HelpOverlay />);
    expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument();
    expect(screen.getByText(/go to dashboard/i)).toBeInTheDocument();
  });
});
