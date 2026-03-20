import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { SavingsOpportunities } from '@/components/ui/SavingsOpportunities';

jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children, ...props }: React.PropsWithChildren & Record<string, unknown>) => (
    <div data-testid={props['data-testid'] as string}>{children}</div>
  ),
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
}));

const getSavingsOpportunitiesMock = jest.fn();
jest.mock('@/api/insights', () => ({
  getSavingsOpportunities: (...args: unknown[]) => getSavingsOpportunitiesMock(...args),
}));

describe('SavingsOpportunities', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows loading state initially', () => {
    getSavingsOpportunitiesMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<SavingsOpportunities month="2026-03" />);
    expect(screen.getByTestId('savings-loading')).toBeInTheDocument();
  });

  it('renders opportunity cards when data is loaded', async () => {
    getSavingsOpportunitiesMock.mockResolvedValue({
      month: '2026-03',
      opportunities: [
        {
          type: 'month_over_month_increase',
          title: 'Dining spending spike',
          description: 'Your Dining spending increased 50% this month.',
          potential_savings: 50.0,
          category: 'Dining',
          trend: { current_month: 150, previous_month: 100, change_pct: 50.0 },
        },
        {
          type: 'high_frequency_small_purchases',
          title: 'Small purchases add up',
          description: 'You made 10 small purchases totalling $50.',
          potential_savings: 25.0,
          category: 'Coffee',
          trend: { transaction_count: 10, total_amount: 50 },
        },
      ],
    });

    render(<SavingsOpportunities month="2026-03" />);
    await waitFor(() => expect(getSavingsOpportunitiesMock).toHaveBeenCalledWith({ month: '2026-03' }));
    await waitFor(() => expect(screen.getByTestId('savings-opportunities')).toBeInTheDocument());

    const cards = screen.getAllByTestId('savings-opportunity-card');
    expect(cards).toHaveLength(2);
    expect(screen.getByText(/dining spending spike/i)).toBeInTheDocument();
    expect(screen.getByText(/small purchases add up/i)).toBeInTheDocument();
  });

  it('shows empty state when no opportunities', async () => {
    getSavingsOpportunitiesMock.mockResolvedValue({
      month: '2026-03',
      opportunities: [],
    });

    render(<SavingsOpportunities month="2026-03" />);
    await waitFor(() => expect(screen.getByTestId('savings-empty')).toBeInTheDocument());
    expect(screen.getByText(/no savings opportunities found/i)).toBeInTheDocument();
  });

  it('shows error state on failure', async () => {
    getSavingsOpportunitiesMock.mockRejectedValue(new Error('Network error'));

    render(<SavingsOpportunities month="2026-03" />);
    await waitFor(() => expect(screen.getByTestId('savings-error')).toBeInTheDocument());
    expect(screen.getByText(/network error/i)).toBeInTheDocument();
  });

  it('re-fetches when month prop changes', async () => {
    getSavingsOpportunitiesMock.mockResolvedValue({
      month: '2026-03',
      opportunities: [],
    });

    const { rerender } = render(<SavingsOpportunities month="2026-03" />);
    await waitFor(() => expect(getSavingsOpportunitiesMock).toHaveBeenCalledWith({ month: '2026-03' }));

    getSavingsOpportunitiesMock.mockResolvedValue({
      month: '2026-04',
      opportunities: [],
    });

    rerender(<SavingsOpportunities month="2026-04" />);
    await waitFor(() => expect(getSavingsOpportunitiesMock).toHaveBeenCalledWith({ month: '2026-04' }));
    expect(getSavingsOpportunitiesMock).toHaveBeenCalledTimes(2);
  });
});
