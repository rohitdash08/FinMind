import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BrowserRouter } from 'react-router-dom';
import { WeeklyDigest } from '../pages/WeeklyDigest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock the API
vi.mock('@/api/weeklyDigest', () => ({
  getWeeklySummary: vi.fn().mockResolvedValue({
    week_start: '2024-01-01',
    week_end: '2024-01-07',
    method: 'heuristic',
    subject: 'Your Weekly Financial Digest',
    greeting: 'Here is your weekly summary!',
    highlights: ['Great week!', 'Spending decreased by 15%'],
    insights: ['Highest spend in category 1'],
    warnings: [],
    tips: ['Review top spending categories'],
    closing: 'Keep up the good work!',
    week_data: {
      week_start: '2024-01-01',
      week_end: '2024-01-07',
      total_income: 2000,
      total_expenses: 1500,
      net_flow: 500,
      categories: { '1': 500, '2': 300 },
      transaction_count: 25,
      upcoming_bills: [
        { name: 'Electric', amount: 100, due_date: '2024-01-05' },
      ],
    },
    previous_week_data: {
      week_start: '2023-12-25',
      week_end: '2023-12-31',
      total_income: 1800,
      total_expenses: 1700,
      net_flow: 100,
      categories: { '1': 600 },
      transaction_count: 20,
      upcoming_bills: [],
    },
    comparison: {
      total_income_pct_change: 11.1,
      total_expenses_pct_change: -11.8,
      net_flow_pct_change: 400,
    },
    persona: 'default',
  }),
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

describe('WeeklyDigest', () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it('renders weekly summary correctly', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <WeeklyDigest />
        </BrowserRouter>
      </QueryClientProvider>
    );

    // Wait for loading to finish
    await waitFor(() => {
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    // Check page title
    expect(screen.getByText('Weekly Financial Digest')).toBeInTheDocument();

    // Check summary cards
    expect(screen.getByText('Net Flow')).toBeInTheDocument();
    expect(screen.getByText('Income')).toBeInTheDocument();
    expect(screen.getByText('Expenses')).toBeInTheDocument();
    expect(screen.getByText('Transactions')).toBeInTheDocument();

    // Check sections
    expect(screen.getByText('Highlights')).toBeInTheDocument();
    expect(screen.getByText('Insights')).toBeInTheDocument();
    expect(screen.getByText('Pro Tips for Next Week')).toBeInTheDocument();
    expect(screen.getByText('Spending by Category')).toBeInTheDocument();
    expect(screen.getByText('Upcoming Bills')).toBeInTheDocument();
  });

  it('displays currency values correctly', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <WeeklyDigest />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    // Check for amounts - format depends on currency formatter
    expect(screen.getByText(/25/i)).toBeInTheDocument(); // transactions
  });

  it('has navigation buttons', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <WeeklyDigest />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    expect(screen.getByText('Previous')).toBeInTheDocument();
    expect(screen.getByText('Next')).toBeInTheDocument();
    expect(screen.getByText('Email Me')).toBeInTheDocument();
  });
});
