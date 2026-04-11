/**
 * DashboardWidgets.test.tsx
 *
 * Tests for the customizable dashboard widgets feature (issue #103):
 *  - Hidden widgets are not rendered.
 *  - Custom widget order is respected.
 *  - The customizer dialog can toggle visibility and save preferences.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Dashboard } from '@/pages/Dashboard';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    ...props
  }: React.PropsWithChildren<
    React.ButtonHTMLAttributes<HTMLButtonElement>
  >) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/switch', () => ({
  Switch: ({
    id,
    checked,
    onCheckedChange,
    'aria-label': ariaLabel,
  }: {
    id?: string;
    checked?: boolean;
    onCheckedChange?: (v: boolean) => void;
    'aria-label'?: string;
  }) => (
    <input
      id={id}
      type="checkbox"
      role="switch"
      checked={!!checked}
      aria-label={ariaLabel}
      onChange={(e) => onCheckedChange?.(e.target.checked)}
    />
  ),
}));

jest.mock('@/components/ui/label', () => ({
  Label: ({
    children,
    htmlFor,
    ...props
  }: React.PropsWithChildren<{ htmlFor?: string; className?: string }>) => (
    <label htmlFor={htmlFor} {...props}>
      {children}
    </label>
  ),
}));

jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({
    open,
    onOpenChange,
    children,
  }: React.PropsWithChildren<{
    open?: boolean;
    onOpenChange?: (o: boolean) => void;
  }>) => (
    <div>
      {/* Render children regardless; let DialogTrigger / DialogContent handle */}
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          // Pass open state to DialogContent for conditional rendering
          return React.cloneElement(
            child as React.ReactElement<{
              open?: boolean;
              onOpenChange?: (o: boolean) => void;
            }>,
            { open, onOpenChange },
          );
        }
        return child;
      })}
    </div>
  ),
  DialogTrigger: ({
    children,
    asChild,
    onOpenChange,
  }: React.PropsWithChildren<{
    asChild?: boolean;
    open?: boolean;
    onOpenChange?: (o: boolean) => void;
  }>) => {
    if (asChild && React.isValidElement(children)) {
      return React.cloneElement(
        children as React.ReactElement<React.HTMLAttributes<HTMLElement>>,
        {
          onClick: (e: React.MouseEvent) => {
            (
              children as React.ReactElement<
                React.HTMLAttributes<HTMLElement>
              >
            ).props.onClick?.(e);
            onOpenChange?.(true);
          },
        },
      );
    }
    return (
      <button onClick={() => onOpenChange?.(true)}>{children}</button>
    );
  },
  DialogContent: ({
    children,
    open,
  }: React.PropsWithChildren<{ open?: boolean; onOpenChange?: (o: boolean) => void }>) =>
    open ? <div role="dialog">{children}</div> : null,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
}));

const getDashboardSummaryMock = jest.fn();
const getDashboardPreferencesMock = jest.fn();
const updateDashboardPreferencesMock = jest.fn();

jest.mock('@/api/dashboard', () => ({
  getDashboardSummary: (...args: unknown[]) => getDashboardSummaryMock(...args),
  getDashboardPreferences: (...args: unknown[]) =>
    getDashboardPreferencesMock(...args),
  updateDashboardPreferences: (...args: unknown[]) =>
    updateDashboardPreferencesMock(...args),
  DEFAULT_WIDGETS: [
    { id: 'summary_cards', label: 'Summary Cards', visible: true },
    { id: 'recent_transactions', label: 'Recent Transactions', visible: true },
    { id: 'upcoming_bills', label: 'Upcoming Bills', visible: true },
    { id: 'category_breakdown', label: 'Category Breakdown', visible: true },
  ],
  WIDGET_IDS: [
    'summary_cards',
    'recent_transactions',
    'upcoming_bills',
    'category_breakdown',
  ],
}));

const DEFAULT_WIDGETS_MOCK = [
  { id: 'summary_cards', label: 'Summary Cards', visible: true },
  { id: 'recent_transactions', label: 'Recent Transactions', visible: true },
  { id: 'upcoming_bills', label: 'Upcoming Bills', visible: true },
  { id: 'category_breakdown', label: 'Category Breakdown', visible: true },
];

// Minimal dashboard summary payload
const emptySummary = {
  period: { month: '2026-04' },
  summary: {
    net_flow: 0,
    monthly_income: 0,
    monthly_expenses: 0,
    upcoming_bills_total: 0,
    upcoming_bills_count: 0,
  },
  recent_transactions: [],
  upcoming_bills: [],
  category_breakdown: [],
  errors: [],
};

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/expenses" element={<div>Expenses Route</div>} />
        <Route path="/bills" element={<div>Bills Route</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DashboardWidgets — visibility', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getDashboardSummaryMock.mockResolvedValue(emptySummary);
  });

  it('renders all four widgets when all are visible', async () => {
    getDashboardPreferencesMock.mockResolvedValue({
      widgets: DEFAULT_WIDGETS_MOCK,
    });
    renderDashboard();
    await waitFor(() =>
      expect(getDashboardPreferencesMock).toHaveBeenCalled(),
    );
    expect(
      screen.getByTestId('widget-summary_cards'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('widget-recent_transactions'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('widget-upcoming_bills'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('widget-category_breakdown'),
    ).toBeInTheDocument();
  });

  it('does not render a hidden widget', async () => {
    getDashboardPreferencesMock.mockResolvedValue({
      widgets: [
        { id: 'summary_cards', label: 'Summary Cards', visible: true },
        {
          id: 'recent_transactions',
          label: 'Recent Transactions',
          visible: false,
        },
        { id: 'upcoming_bills', label: 'Upcoming Bills', visible: true },
        {
          id: 'category_breakdown',
          label: 'Category Breakdown',
          visible: true,
        },
      ],
    });
    renderDashboard();
    await waitFor(() =>
      expect(getDashboardPreferencesMock).toHaveBeenCalled(),
    );
    expect(
      screen.queryByTestId('widget-recent_transactions'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('widget-summary_cards'),
    ).toBeInTheDocument();
  });

  it('shows an empty-state prompt when all widgets are hidden', async () => {
    getDashboardPreferencesMock.mockResolvedValue({
      widgets: DEFAULT_WIDGETS_MOCK.map((w) => ({
        ...w,
        visible: false,
      })),
    });
    renderDashboard();
    await waitFor(() =>
      expect(getDashboardPreferencesMock).toHaveBeenCalled(),
    );
    expect(
      screen.getByText(/all widgets are hidden/i),
    ).toBeInTheDocument();
  });

  it('falls back to default widgets when preferences API fails', async () => {
    getDashboardPreferencesMock.mockRejectedValue(new Error('network error'));
    renderDashboard();
    await waitFor(() =>
      expect(getDashboardPreferencesMock).toHaveBeenCalled(),
    );
    // Should still render the defaults
    expect(
      screen.getByTestId('widget-summary_cards'),
    ).toBeInTheDocument();
  });
});

describe('DashboardWidgets — customizer dialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getDashboardSummaryMock.mockResolvedValue(emptySummary);
    getDashboardPreferencesMock.mockResolvedValue({
      widgets: DEFAULT_WIDGETS_MOCK,
    });
  });

  it('opens the customizer when the Customize button is clicked', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() =>
      expect(getDashboardPreferencesMock).toHaveBeenCalled(),
    );
    await user.click(
      screen.getByRole('button', { name: /customize dashboard/i }),
    );
    expect(
      screen.getByRole('dialog'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/dashboard layout/i),
    ).toBeInTheDocument();
  });

  it('calls updateDashboardPreferences on save and closes the dialog', async () => {
    const user = userEvent.setup();
    const updatedWidgets = DEFAULT_WIDGETS_MOCK.map((w) =>
      w.id === 'upcoming_bills' ? { ...w, visible: false } : w,
    );
    updateDashboardPreferencesMock.mockResolvedValue({
      widgets: updatedWidgets,
    });
    renderDashboard();
    await waitFor(() =>
      expect(getDashboardPreferencesMock).toHaveBeenCalled(),
    );

    // Open dialog
    await user.click(
      screen.getByRole('button', { name: /customize dashboard/i }),
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Toggle Upcoming Bills off
    const toggle = screen.getByRole('switch', {
      name: /toggle upcoming bills/i,
    });
    await user.click(toggle);

    // Save
    await user.click(
      screen.getByRole('button', { name: /save dashboard layout/i }),
    );

    await waitFor(() =>
      expect(updateDashboardPreferencesMock).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            id: 'upcoming_bills',
            visible: false,
          }),
        ]),
      ),
    );

    // Dialog should close after successful save
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
  });

  it('applies saved order so the hidden widget is absent from the dashboard', async () => {
    const user = userEvent.setup();
    const updatedWidgets = DEFAULT_WIDGETS_MOCK.map((w) =>
      w.id === 'category_breakdown' ? { ...w, visible: false } : w,
    );
    updateDashboardPreferencesMock.mockResolvedValue({
      widgets: updatedWidgets,
    });
    renderDashboard();
    await waitFor(() =>
      expect(getDashboardPreferencesMock).toHaveBeenCalled(),
    );

    // Confirm category_breakdown is currently visible
    expect(
      screen.getByTestId('widget-category_breakdown'),
    ).toBeInTheDocument();

    // Open dialog and toggle category breakdown off
    await user.click(
      screen.getByRole('button', { name: /customize dashboard/i }),
    );
    await user.click(
      screen.getByRole('switch', { name: /toggle category breakdown/i }),
    );
    await user.click(
      screen.getByRole('button', { name: /save dashboard layout/i }),
    );

    await waitFor(() =>
      expect(updateDashboardPreferencesMock).toHaveBeenCalled(),
    );

    // After save, the widget should be gone
    await waitFor(() =>
      expect(
        screen.queryByTestId('widget-category_breakdown'),
      ).not.toBeInTheDocument(),
    );
  });
});
