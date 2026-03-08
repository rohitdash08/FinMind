import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import WeeklyDigest from '../pages/WeeklyDigest';

const mockSummary = {
  week: { start: '2026-03-02', end: '2026-03-08' },
  totals: { income: 5000, expenses: 1200, net: 3800, transaction_count: 12 },
  daily_breakdown: [
    { date: '2026-03-02', income: 0, expenses: 100 },
    { date: '2026-03-03', income: 5000, expenses: 200 },
    { date: '2026-03-04', income: 0, expenses: 300 },
    { date: '2026-03-05', income: 0, expenses: 150 },
    { date: '2026-03-06', income: 0, expenses: 250 },
    { date: '2026-03-07', income: 0, expenses: 100 },
    { date: '2026-03-08', income: 0, expenses: 100 },
  ],
  category_breakdown: [
    { category_id: 1, category_name: 'Food', amount: 600, count: 5, share_pct: 50 },
    { category_id: 2, category_name: 'Transport', amount: 600, count: 7, share_pct: 50 },
  ],
  top_expenses: [
    { id: 1, description: 'Big Purchase', amount: 300, date: '2026-03-04', category_id: 1, currency: 'INR' },
  ],
  upcoming_bills: [
    { id: 1, name: 'Internet', amount: 999, currency: 'INR', next_due_date: '2026-03-10', cadence: 'MONTHLY' },
  ],
  trends: {
    expense_change_pct: -15.2,
    income_change_pct: 10.0,
    previous_week_expenses: 1414,
    previous_week_income: 4545,
  },
};

vi.mock('../api/weekly-summary', () => ({
  getWeeklySummary: vi.fn(() => Promise.resolve(mockSummary)),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <WeeklyDigest />
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

describe('WeeklyDigest page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page title', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Weekly Digest')).toBeTruthy();
    });
  });

  it('shows summary cards with correct data', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Weekly Income')).toBeTruthy();
      expect(screen.getByText('Weekly Expenses')).toBeTruthy();
      expect(screen.getByText('Net Flow')).toBeTruthy();
      expect(screen.getByText('Transactions')).toBeTruthy();
    });
  });

  it('shows top expenses', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Big Purchase')).toBeTruthy();
    });
  });

  it('shows upcoming bills', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Internet')).toBeTruthy();
    });
  });

  it('shows category breakdown', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Food')).toBeTruthy();
      expect(screen.getByText('Transport')).toBeTruthy();
    });
  });

  it('shows week navigation buttons', () => {
    renderPage();
    expect(screen.getByText('This Week')).toBeTruthy();
  });
});
