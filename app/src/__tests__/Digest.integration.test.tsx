import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Digest from '../pages/Digest';
import * as digestApi from '../api/digest';

// Mock the API
jest.mock('../api/digest');

const mockDigest: digestApi.WeeklyDigest = {
  period: {
    week_start: '2026-03-16',
    week_end: '2026-03-22',
  },
  summary: {
    total_income: 3000,
    total_expenses: 850,
    net_flow: 2150,
    transaction_count: 7,
  },
  comparison: {
    prev_week_expenses: 700,
    prev_week_income: 3000,
    week_over_week_change_pct: 21.43,
  },
  category_breakdown: [
    { category_id: 1, category_name: 'Food', amount: 400, share_pct: 47.06 },
    { category_id: 2, category_name: 'Transport', amount: 250, share_pct: 29.41 },
    { category_id: null, category_name: 'Uncategorized', amount: 200, share_pct: 23.53 },
  ],
  daily_spending: [
    { date: '2026-03-16', amount: 120 },
    { date: '2026-03-17', amount: 200 },
    { date: '2026-03-18', amount: 0 },
    { date: '2026-03-19', amount: 150 },
    { date: '2026-03-20', amount: 80 },
    { date: '2026-03-21', amount: 300 },
    { date: '2026-03-22', amount: 0 },
  ],
  top_transactions: [
    { id: 1, amount: 300, description: 'Restaurant dinner', date: '2026-03-21', category_id: 1 },
    { id: 2, amount: 200, description: 'Uber rides', date: '2026-03-17', category_id: 2 },
  ],
  insights: [
    'Spending is up 21.4% compared to the previous week.',
    'You saved 2,150.00 this week (income exceeded expenses).',
    'Your biggest spending category was Food at 400.00 (47% of total).',
  ],
};

const mockWeeks: digestApi.DigestWeek[] = [
  { week_start: '2026-03-16', week_end: '2026-03-22' },
  { week_start: '2026-03-09', week_end: '2026-03-15' },
];

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Digest page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (digestApi.getAvailableWeeks as jest.Mock).mockResolvedValue(mockWeeks);
    (digestApi.getWeeklyDigest as jest.Mock).mockResolvedValue(mockDigest);
  });

  it('renders the page title', async () => {
    renderWithProviders(<Digest />);
    expect(screen.getByText('Weekly Digest')).toBeInTheDocument();
  });

  it('displays summary cards after loading', async () => {
    renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(screen.getByText('Net Flow')).toBeInTheDocument();
    });
    expect(screen.getByText('Income')).toBeInTheDocument();
    expect(screen.getByText('Expenses')).toBeInTheDocument();
    expect(screen.getByText('Prev Week')).toBeInTheDocument();
  });

  it('displays insights', async () => {
    renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(screen.getByText('Insights')).toBeInTheDocument();
    });
    expect(screen.getByText(/Spending is up 21.4%/)).toBeInTheDocument();
    expect(screen.getByText(/saved/i)).toBeInTheDocument();
  });

  it('displays category breakdown', async () => {
    renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(screen.getByText('Food')).toBeInTheDocument();
    });
    expect(screen.getByText('Transport')).toBeInTheDocument();
  });

  it('displays top transactions', async () => {
    renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(screen.getByText('Restaurant dinner')).toBeInTheDocument();
    });
    expect(screen.getByText('Uber rides')).toBeInTheDocument();
  });

  it('shows week navigation controls', async () => {
    renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(screen.getByLabelText('Older week')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Newer week')).toBeInTheDocument();
  });

  it('handles API error gracefully', async () => {
    (digestApi.getWeeklyDigest as jest.Mock).mockRejectedValue(new Error('Network error'));
    renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });
  });
});
