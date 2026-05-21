import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Analytics } from '@/pages/Analytics';

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock('@/components/ui/input', () => ({
  Input: ({ ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));
jest.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.PropsWithChildren & React.LabelHTMLAttributes<HTMLLabelElement>) => (
    <label {...props}>{children}</label>
  ),
}));
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

const getBudgetSuggestionMock = jest.fn();
const getWeeklySummaryMock = jest.fn();
jest.mock('@/api/insights', () => ({
  getBudgetSuggestion: (...args: unknown[]) => getBudgetSuggestionMock(...args),
  getWeeklySummary: (...args: unknown[]) => getWeeklySummaryMock(...args),
}));

describe('Analytics integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getBudgetSuggestionMock.mockResolvedValue({
      month: '2026-02',
      suggested_total: 1200,
      breakdown: { needs: 600, wants: 360, savings: 240 },
      tips: ['Tip A', 'Tip B'],
      analytics: {
        month_over_month_change_pct: 12.5,
        current_month_expenses: 1000,
        previous_month_expenses: 888.89,
        top_categories: [],
      },
      persona: 'Balanced coach',
      method: 'heuristic',
      warnings: [],
    });
    getWeeklySummaryMock.mockResolvedValue({
      period: {
        week_start: '2026-05-18',
        week_end: '2026-05-24',
        previous_week_start: '2026-05-11',
        previous_week_end: '2026-05-17',
      },
      currency: 'USD',
      summary: {
        income: 1500,
        expenses: 420,
        net_flow: 1080,
        transaction_count: 4,
        average_daily_expense: 60,
        savings_rate_pct: 72,
      },
      comparison: {
        previous_expenses: 500,
        expense_change: -80,
        expense_change_pct: -16,
        trend: 'down',
      },
      category_breakdown: [
        {
          category_id: 1,
          category_name: 'Groceries',
          amount: 220,
          share_pct: 52.38,
          previous_amount: 240,
          change_pct: -8.33,
          transaction_count: 2,
        },
      ],
      daily_breakdown: [
        { date: '2026-05-18', day: 'Mon', expenses: 0 },
        { date: '2026-05-19', day: 'Tue', expenses: 220 },
        { date: '2026-05-20', day: 'Wed', expenses: 0 },
        { date: '2026-05-21', day: 'Thu', expenses: 200 },
        { date: '2026-05-22', day: 'Fri', expenses: 0 },
        { date: '2026-05-23', day: 'Sat', expenses: 0 },
        { date: '2026-05-24', day: 'Sun', expenses: 0 },
      ],
      largest_expenses: [],
      upcoming_bills: [],
      highlights: ['Expenses were lower than last week.'],
      insights: ['Net flow stayed positive.'],
      recommendations: ['Keep the current weekly pattern.'],
    });
  });

  it('loads and renders insights data', async () => {
    render(<Analytics />);
    await waitFor(() => expect(getBudgetSuggestionMock).toHaveBeenCalled());
    expect(screen.getByText(/live spending analytics/i)).toBeInTheDocument();
    expect(await screen.findByText(/weekly smart digest/i)).toBeInTheDocument();
    expect(screen.getByText(/suggested budget/i)).toBeInTheDocument();
    expect(screen.getByText(/tip a/i)).toBeInTheDocument();
    expect(screen.getByText(/keep the current weekly pattern/i)).toBeInTheDocument();
  });

  it('refreshes insights with month/persona/key controls', async () => {
    render(<Analytics />);
    await waitFor(() => expect(getBudgetSuggestionMock).toHaveBeenCalledTimes(1));

    await userEvent.clear(screen.getByLabelText(/analytics month/i));
    await userEvent.type(screen.getByLabelText(/analytics month/i), '2026-01');
    await userEvent.clear(screen.getByLabelText(/analytics week start/i));
    await userEvent.type(screen.getByLabelText(/analytics week start/i), '2026-05-18');
    await userEvent.type(screen.getByLabelText(/analytics currency/i), 'usd');
    await userEvent.selectOptions(screen.getByLabelText(/analytics persona/i), 'Debt-focused planner');
    await userEvent.type(screen.getByLabelText(/gemini api key/i), 'abc123');
    await userEvent.click(screen.getByRole('button', { name: /refresh insights/i }));

    await waitFor(() =>
      expect(getBudgetSuggestionMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          month: '2026-01',
          persona: 'Debt-focused planner',
          geminiApiKey: 'abc123',
        }),
      ),
    );
    await waitFor(() =>
      expect(getWeeklySummaryMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          weekStart: '2026-05-18',
          currency: 'USD',
        }),
      ),
    );
  });
});
