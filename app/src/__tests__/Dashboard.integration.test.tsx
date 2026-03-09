import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Dashboard } from '@/pages/Dashboard';

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const getDashboardSummaryMock = jest.fn();
const getMultiAccountOverviewMock = jest.fn();
jest.mock('@/api/dashboard', () => ({
  getDashboardSummary: (...args: unknown[]) => getDashboardSummaryMock(...args),
  getMultiAccountOverview: (...args: unknown[]) => getMultiAccountOverviewMock(...args),
}));

describe('Dashboard integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getMultiAccountOverviewMock.mockResolvedValue({
      period: { month: '2026-02' },
      aggregated: {
        monthly_income: 3200,
        monthly_expenses: 550,
        net_flow: 2650,
        upcoming_bills_total: 49.99,
        upcoming_bills_count: 1,
        account_count: 2,
      },
      accounts: [
        {
          account_key: 'USD',
          summary: {
            net_flow: 1900,
            monthly_income: 2200,
            monthly_expenses: 300,
            upcoming_bills_total: 49.99,
            upcoming_bills_count: 1,
          },
        },
        {
          account_key: 'EUR',
          summary: {
            net_flow: 750,
            monthly_income: 1000,
            monthly_expenses: 250,
            upcoming_bills_total: 0,
            upcoming_bills_count: 0,
          },
        },
      ],
      errors: [],
    });
  });

  it('renders summary, transactions and upcoming bills from backend payload', async () => {
    getDashboardSummaryMock.mockResolvedValue({
      period: { month: '2026-02' },
      summary: {
        net_flow: 2500,
        monthly_income: 3000,
        monthly_expenses: 500,
        upcoming_bills_total: 49.99,
        upcoming_bills_count: 1,
      },
      recent_transactions: [
        {
          id: 1,
          description: 'Salary',
          amount: 3000,
          date: '2026-02-10',
          type: 'INCOME',
          category_id: null,
          currency: 'USD',
        },
      ],
      upcoming_bills: [
        {
          id: 1,
          name: 'Internet',
          amount: 49.99,
          currency: 'USD',
          next_due_date: '2026-02-20',
          cadence: 'MONTHLY',
          channel_email: true,
          channel_whatsapp: false,
        },
      ],
      category_breakdown: [
        {
          category_id: 1,
          category_name: 'Food',
          amount: 500,
          share_pct: 100,
        },
      ],
      errors: [],
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(getDashboardSummaryMock).toHaveBeenCalled());

    expect(screen.getByText(/financial dashboard/i)).toBeInTheDocument();
    expect(await screen.findByText(/salary/i)).toBeInTheDocument();
    expect(await screen.findByText(/internet/i)).toBeInTheDocument();
    expect(screen.getByText(/category breakdown/i)).toBeInTheDocument();
  });

  it('navigates from dashboard action buttons', async () => {
    const user = userEvent.setup();
    getDashboardSummaryMock.mockResolvedValue({
      period: { month: '2026-02' },
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
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/expenses" element={<div>Expenses Route</div>} />
          <Route path="/bills" element={<div>Bills Route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getDashboardSummaryMock).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /add transaction/i }));
    expect(await screen.findByText('Expenses Route')).toBeInTheDocument();
  });

  it('reloads summary when month filter changes', async () => {
    getDashboardSummaryMock.mockResolvedValue({
      period: { month: '2026-02' },
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
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getDashboardSummaryMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText(/dashboard month/i), { target: { value: '2026-01' } });
    await waitFor(() => expect(getDashboardSummaryMock).toHaveBeenLastCalledWith('2026-01'));
  });

  it('shows multi-account combined totals and per-account overview', async () => {
    const currentMonth = new Date().toISOString().slice(0, 7);
    getDashboardSummaryMock.mockResolvedValue({
      period: { month: '2026-02' },
      summary: {
        net_flow: 2650,
        monthly_income: 3200,
        monthly_expenses: 550,
        upcoming_bills_total: 49.99,
        upcoming_bills_count: 1,
      },
      recent_transactions: [],
      upcoming_bills: [],
      category_breakdown: [],
      errors: [],
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getMultiAccountOverviewMock).toHaveBeenCalledWith(currentMonth, undefined));
    expect(screen.getByRole('heading', { name: /account overview/i })).toBeInTheDocument();
    expect((await screen.findAllByText('USD')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('EUR')).length).toBeGreaterThan(0);
    expect(await screen.findByText(/2 account\(s\)/i)).toBeInTheDocument();
  });
});
