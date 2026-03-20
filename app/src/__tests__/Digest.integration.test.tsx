import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Digest } from '../pages/Digest';
import * as digestApi from '../api/digest';

const mockDigest: digestApi.WeeklyDigest = {
  week: '2026-W12',
  period: { start: '2026-03-16', end: '2026-03-22' },
  summary: {
    total_income: 500,
    total_expenses: 200,
    net_flow: 300,
    transaction_count: 5,
  },
  trends: {
    previous_week: '2026-W11',
    previous_income: 400,
    previous_expenses: 180,
    income_change_pct: 25.0,
    expense_change_pct: 11.11,
  },
  category_breakdown: [
    { category_id: 1, category_name: 'Food', amount: 120, share_pct: 60 },
    { category_id: 2, category_name: 'Transport', amount: 80, share_pct: 40 },
  ],
  daily_spending: [
    { date: '2026-03-16', amount: 50 },
    { date: '2026-03-17', amount: 75 },
    { date: '2026-03-18', amount: 75 },
  ],
  transactions: [
    {
      id: 1,
      description: 'Lunch',
      amount: 15,
      date: '2026-03-16',
      type: 'EXPENSE',
      category_id: 1,
      currency: 'INR',
    },
    {
      id: 2,
      description: 'Salary',
      amount: 500,
      date: '2026-03-16',
      type: 'INCOME',
      category_id: null,
      currency: 'INR',
    },
  ],
  upcoming_bills: [
    {
      id: 1,
      name: 'Internet',
      amount: 50,
      currency: 'INR',
      next_due_date: '2026-03-20',
      cadence: 'MONTHLY',
    },
  ],
  insights: [
    'Positive cash flow of 300.00 this week.',
    'Top spending category: Food (60% of total).',
  ],
  method: 'heuristic',
  persona: 'test persona',
};

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>
  );
}

describe('Digest Page', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders digest data after loading', async () => {
    vi.spyOn(digestApi, 'getWeeklyDigest').mockResolvedValue(mockDigest);

    renderWithProviders(<Digest />);

    expect(screen.getByText('Loading weekly digest...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Weekly Digest')).toBeInTheDocument();
    });

    // Summary cards
    await waitFor(() => {
      expect(screen.getByText('Net Flow')).toBeInTheDocument();
      expect(screen.getByText('Income')).toBeInTheDocument();
      expect(screen.getByText('Expenses')).toBeInTheDocument();
      expect(screen.getByText('WoW Spending')).toBeInTheDocument();
    });

    // Insights
    await waitFor(() => {
      expect(screen.getByText('Weekly Insights')).toBeInTheDocument();
      expect(screen.getByText(/Positive cash flow/)).toBeInTheDocument();
    });

    // Transactions
    await waitFor(() => {
      expect(screen.getByText('Lunch')).toBeInTheDocument();
      expect(screen.getByText('Salary')).toBeInTheDocument();
    });

    // Category breakdown
    await waitFor(() => {
      expect(screen.getByText('Food')).toBeInTheDocument();
      expect(screen.getByText('Transport')).toBeInTheDocument();
    });
  });

  it('shows error state on failure', async () => {
    vi.spyOn(digestApi, 'getWeeklyDigest').mockRejectedValue(
      new Error('Network error')
    );

    renderWithProviders(<Digest />);

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('displays bills due this week when present', async () => {
    vi.spyOn(digestApi, 'getWeeklyDigest').mockResolvedValue(mockDigest);

    renderWithProviders(<Digest />);

    await waitFor(() => {
      expect(screen.getByText('Bills Due This Week')).toBeInTheDocument();
      expect(screen.getByText('Internet')).toBeInTheDocument();
    });
  });

  it('hides bills section when none due', async () => {
    vi.spyOn(digestApi, 'getWeeklyDigest').mockResolvedValue({
      ...mockDigest,
      upcoming_bills: [],
    });

    renderWithProviders(<Digest />);

    await waitFor(() => {
      expect(screen.getByText('Weekly Insights')).toBeInTheDocument();
    });

    expect(screen.queryByText('Bills Due This Week')).not.toBeInTheDocument();
  });
});
