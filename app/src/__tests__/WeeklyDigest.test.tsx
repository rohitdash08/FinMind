import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WeeklyDigest } from '../components/WeeklyDigest';
import * as weeklySummaryApi from '../api/weekly-summary';

// Mock the API module
jest.mock('../api/weekly-summary');

const mockWeeklySummary = {
  week_start: '2025-02-17',
  week_end: '2025-02-23',
  total_income: 3500,
  total_expenses: 1200,
  net_flow: 2300,
  transaction_count: 12,
  top_expense_category: {
    name: 'Food & Dining',
    amount: 420,
    percentage: 35,
  },
  comparison_to_last_week: {
    expense_change_pct: -5.2,
    income_change_pct: 2.1,
  },
  insights: [
    {
      type: 'achievement' as const,
      title: 'Great Savings Week!',
      description: 'You saved 65.7% of your income this week.',
      severity: 'positive' as const,
    },
    {
      type: 'tip' as const,
      title: 'Budgeting Tip',
      description: 'Try the 50/30/20 rule: 50% needs, 30% wants, 20% savings.',
      severity: 'neutral' as const,
    },
  ],
  daily_breakdown: [
    { date: '2025-02-17', income: 0, expenses: 150 },
    { date: '2025-02-18', income: 0, expenses: 80 },
    { date: '2025-02-19', income: 0, expenses: 200 },
    { date: '2025-02-20', income: 2800, expenses: 120 },
    { date: '2025-02-21', income: 700, expenses: 350 },
    { date: '2025-02-22', income: 0, expenses: 180 },
    { date: '2025-02-23', income: 0, expenses: 120 },
  ],
};

describe('WeeklyDigest', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (weeklySummaryApi.getWeeklySummary as jest.Mock).mockResolvedValue(mockWeeklySummary);
  });

  it('renders loading state initially', () => {
    render(<WeeklyDigest />);
    expect(screen.getAllByText('...').length).toBeGreaterThan(0);
  });

  it('renders weekly summary data correctly', async () => {
    render(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText(/Weekly Digest/i)).toBeInTheDocument();
    });

    // Check summary stats
    expect(screen.getByText('$3,500.00')).toBeInTheDocument();
    expect(screen.getByText('$1,200.00')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();

    // Check insights
    expect(screen.getByText('Great Savings Week!')).toBeInTheDocument();
    expect(screen.getByText('Budgeting Tip')).toBeInTheDocument();

    // Check comparison badges
    expect(screen.getByText(/5.2% vs last week/i)).toBeInTheDocument();
  });

  it('displays empty state when no transactions', async () => {
    (weeklySummaryApi.getWeeklySummary as jest.Mock).mockResolvedValue({
      ...mockWeeklySummary,
      transaction_count: 0,
      total_income: 0,
      total_expenses: 0,
      net_flow: 0,
      insights: [],
    });

    render(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText('No transactions this week')).toBeInTheDocument();
    });
  });

  it('navigates to previous week when clicking back button', async () => {
    render(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText(/Weekly Digest/i)).toBeInTheDocument();
    });

    const prevButton = screen.getAllByRole('button')[0];
    fireEvent.click(prevButton);

    expect(weeklySummaryApi.getWeeklySummary).toHaveBeenCalledWith(-1);
  });

  it('displays error state when API fails', async () => {
    (weeklySummaryApi.getWeeklySummary as jest.Mock).mockRejectedValue(
      new Error('Network error')
    );

    render(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });
  });

  it('shows correct badge for current week', async () => {
    render(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText('This Week')).toBeInTheDocument();
    });
  });

  it('displays top expense category when available', async () => {
    render(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText(/Food & Dining/i)).toBeInTheDocument();
    });
  });
});
