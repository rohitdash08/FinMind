import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SpendingBreakdown } from '@/components/ui/SpendingBreakdown';

// Mock UI components
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
    <div {...props}>{children}</div>
  ),
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/lib/currency', () => ({
  formatMoney: (v: number) => `$${v.toFixed(2)}`,
}));

const getSpendingBreakdownMock = jest.fn();
jest.mock('@/api/expenses', () => ({
  getSpendingBreakdown: (...args: unknown[]) => getSpendingBreakdownMock(...args),
}));

const MOCK_DATA = {
  essential: {
    total: 500,
    categories: [
      { name: 'Groceries', amount: 300 },
      { name: 'Rent', amount: 200 },
    ],
  },
  discretionary: {
    total: 200,
    categories: [{ name: 'Dining Out', amount: 200 }],
  },
  uncategorized: {
    total: 50,
    categories: [{ name: 'Miscellaneous', amount: 50 }],
  },
  period_total: 750,
};

describe('SpendingBreakdown', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getSpendingBreakdownMock.mockResolvedValue(MOCK_DATA);
  });

  it('shows loading state initially', () => {
    getSpendingBreakdownMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<SpendingBreakdown />);
    expect(screen.getByTestId('spending-breakdown-loading')).toBeInTheDocument();
  });

  it('renders breakdown data after loading', async () => {
    render(<SpendingBreakdown />);
    await waitFor(() => expect(screen.getByTestId('spending-breakdown')).toBeInTheDocument());

    // Title
    expect(screen.getByText(/essential vs discretionary spending/i)).toBeInTheDocument();

    // Totals rendered
    expect(screen.getByText('$500.00')).toBeInTheDocument();
    expect(screen.getByText('$200.00')).toBeInTheDocument();

    // Percentages
    expect(screen.getByText('66.7%')).toBeInTheDocument();
    expect(screen.getByText('26.7%')).toBeInTheDocument();

    // Ratio
    expect(screen.getByText('2.50')).toBeInTheDocument();
  });

  it('expands and collapses category details', async () => {
    const user = userEvent.setup();
    render(<SpendingBreakdown />);
    await waitFor(() => expect(screen.getByTestId('spending-breakdown')).toBeInTheDocument());

    const toggleBtn = screen.getByTestId('toggle-essential');
    expect(toggleBtn).toHaveTextContent(/show 2 categories/i);

    await user.click(toggleBtn);
    const list = screen.getByTestId('list-essential');
    expect(list).toBeInTheDocument();
    expect(screen.getByText('Groceries')).toBeInTheDocument();
    expect(screen.getByText('Rent')).toBeInTheDocument();

    // Collapse
    await user.click(toggleBtn);
    expect(screen.queryByTestId('list-essential')).not.toBeInTheDocument();
  });

  it('shows error state on API failure', async () => {
    getSpendingBreakdownMock.mockRejectedValue(new Error('Network error'));
    render(<SpendingBreakdown />);
    await waitFor(() => expect(screen.getByTestId('spending-breakdown-error')).toBeInTheDocument());
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('handles empty data gracefully', async () => {
    getSpendingBreakdownMock.mockResolvedValue({
      essential: { total: 0, categories: [] },
      discretionary: { total: 0, categories: [] },
      uncategorized: { total: 0, categories: [] },
      period_total: 0,
    });
    render(<SpendingBreakdown />);
    await waitFor(() => expect(screen.getByTestId('spending-breakdown')).toBeInTheDocument());
    // No data text from donut
    expect(screen.getByText('No data')).toBeInTheDocument();
  });
});
