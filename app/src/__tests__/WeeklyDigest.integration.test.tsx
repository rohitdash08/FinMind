import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import WeeklyDigest from '@/pages/WeeklyDigest';

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));
jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <span {...props}>{children}</span>
  ),
}));
jest.mock('@/components/ui/progress', () => ({
  Progress: ({ value, ...props }: { value: number } & React.HTMLAttributes<HTMLDivElement>) => (
    <div role="progressbar" aria-valuenow={value} {...props} />
  ),
}));
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <div {...props}>{children}</div>
  ),
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLHeadingElement>) => (
    <h3 {...props}>{children}</h3>
  ),
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  FinancialCardContent: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <div {...props}>{children}</div>
  ),
}));
jest.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

const digestMock = jest.fn();
const sendEmailMock = jest.fn();

jest.mock('@/api/insights', () => ({
  getWeeklyDigest: (...args: unknown[]) => digestMock(...args),
  sendWeeklyDigestEmail: (...args: unknown[]) => sendEmailMock(...args),
}));

beforeEach(() => {
  jest.spyOn(console, 'error').mockImplementation(() => {});
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

const mockDigest = {
  period: {
    week_start: '2026-03-15',
    week_end: '2026-03-21',
    prev_week_start: '2026-03-08',
    prev_week_end: '2026-03-14',
  },
  summary: {
    total_expenses: 350,
    total_income: 500,
    net_flow: 150,
    prev_week_expenses: 400,
    prev_week_income: 500,
    wow_change_pct: -12.5,
    trend: 'down' as const,
    transaction_count: 8,
  },
  category_breakdown: [
    { category_id: 1, category_name: 'Food', amount: 200, count: 5, share_pct: 57.1 },
    { category_id: 2, category_name: 'Transport', amount: 150, count: 3, share_pct: 42.9 },
  ],
  top_categories: [
    { category_id: 1, category_name: 'Food', amount: 200, count: 5, share_pct: 57.1 },
    { category_id: 2, category_name: 'Transport', amount: 150, count: 3, share_pct: 42.9 },
  ],
  daily_spending: [
    { date: '2026-03-15', amount: 50 },
    { date: '2026-03-16', amount: 75 },
    { date: '2026-03-17', amount: 0 },
    { date: '2026-03-18', amount: 100 },
    { date: '2026-03-19', amount: 25 },
    { date: '2026-03-20', amount: 50 },
    { date: '2026-03-21', amount: 50 },
  ],
  upcoming_bills: [],
  insights: ['Great job! You reduced spending by 12.5% compared to last week.'],
};

describe('WeeklyDigest page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders digest with summary data', async () => {
    digestMock.mockResolvedValue(mockDigest);
    renderWithProviders(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText('$350.00')).toBeInTheDocument();
    });
    expect(screen.getByText('$500.00')).toBeInTheDocument();
    expect(screen.getByText('$150.00')).toBeInTheDocument();
    expect(screen.getByText('-12.5%')).toBeInTheDocument();
    expect(screen.getByText('Spending Down')).toBeInTheDocument();
  });

  it('renders top categories', async () => {
    digestMock.mockResolvedValue(mockDigest);
    renderWithProviders(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText('Food')).toBeInTheDocument();
    });
    expect(screen.getByText('Transport')).toBeInTheDocument();
  });

  it('renders insights', async () => {
    digestMock.mockResolvedValue(mockDigest);
    renderWithProviders(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText(/reduced spending by 12.5%/)).toBeInTheDocument();
    });
  });

  it('shows email digest button', async () => {
    digestMock.mockResolvedValue(mockDigest);
    renderWithProviders(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText(/email digest/i)).toBeInTheDocument();
    });
  });

  it('shows week navigation', async () => {
    digestMock.mockResolvedValue(mockDigest);
    renderWithProviders(<WeeklyDigest />);

    await waitFor(() => {
      expect(screen.getByText('2026-03-15 — 2026-03-21')).toBeInTheDocument();
    });
  });
});
