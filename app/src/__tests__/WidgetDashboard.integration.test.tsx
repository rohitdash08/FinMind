import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Dashboard } from '@/pages/Dashboard';

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const getDashboardSummaryMock = jest.fn();
jest.mock('@/api/dashboard', () => ({
  getDashboardSummary: (...args: unknown[]) => getDashboardSummaryMock(...args),
}));

function buildMockData() {
  return {
    period: { month: '2026-02' },
    summary: {
      net_flow: 1500,
      monthly_income: 5000,
      monthly_expenses: 3500,
      upcoming_bills_total: 300,
      upcoming_bills_count: 3,
    },
    recent_transactions: [],
    upcoming_bills: [],
    category_breakdown: [
      { category_id: 1, category_name: 'Food', amount: 1200, share_pct: 34.3 },
      { category_id: 2, category_name: 'Transport', amount: 800, share_pct: 22.9 },
    ],
    errors: [],
  };
}

describe('WidgetDashboard integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getDashboardSummaryMock.mockResolvedValue(buildMockData());
  });

  it('renders with default widgets', async () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getDashboardSummaryMock).toHaveBeenCalled());
    expect(screen.getByText(/customize widgets/i)).toBeInTheDocument();
    expect(screen.getByText(/summary metrics/i)).toBeInTheDocument();
    expect(screen.getByText(/spending overview/i)).toBeInTheDocument();
  });

  it('enters and exits edit mode', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getDashboardSummaryMock).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /customize widgets/i }));
    expect(screen.getByRole('button', { name: /done/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /done/i }));
    expect(screen.getByRole('button', { name: /customize widgets/i })).toBeInTheDocument();
  });

  it('shows add widget panel in edit mode', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getDashboardSummaryMock).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /customize widgets/i }));
    expect(screen.getByText(/add widget/i)).toBeInTheDocument();
  });
});
