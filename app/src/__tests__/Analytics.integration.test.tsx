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
        week_start: '2026-05-04',
        week_end: '2026-05-10',
        previous_week_start: '2026-04-27',
        currency: 'USD',
      },
      summary: {
        income: 1000,
        expenses: 250,
        net_flow: 750,
        transaction_count: 4,
        average_daily_expense: 35.71,
      },
      previous_week: {
        income: 0,
        expenses: 70,
        net_flow: -70,
        expense_delta: 180,
        expense_delta_pct: 257.14,
      },
      daily_breakdown: [],
      category_breakdown: [
        {
          category_id: 1,
          category_name: 'Food',
          amount: 200,
          transaction_count: 2,
          share_pct: 80,
          previous_amount: 70,
          change_amount: 130,
          change_pct: 185.71,
        },
      ],
      upcoming_bills: [
        {
          id: 1,
          name: 'Internet',
          amount: 45,
          currency: 'USD',
          next_due_date: '2026-05-09',
          cadence: 'MONTHLY',
          autopay_enabled: false,
        },
      ],
      insights: [
        {
          type: 'top_category',
          severity: 'info',
          message: 'Food is the top spending category at 80% of weekly expenses.',
        },
      ],
    });
  });

  it('loads and renders insights data', async () => {
    render(<Analytics />);
    await waitFor(() => expect(getBudgetSuggestionMock).toHaveBeenCalled());
    await waitFor(() => expect(getWeeklySummaryMock).toHaveBeenCalled());
    expect(screen.getByText(/live spending analytics/i)).toBeInTheDocument();
    expect(screen.getByText(/weekly digest/i)).toBeInTheDocument();
    expect(screen.getByText(/food is the top spending category/i)).toBeInTheDocument();
    expect(screen.getByText(/suggested budget/i)).toBeInTheDocument();
    expect(screen.getByText(/tip a/i)).toBeInTheDocument();
  });

  it('refreshes insights with month/persona/key controls', async () => {
    render(<Analytics />);
    await waitFor(() => expect(getBudgetSuggestionMock).toHaveBeenCalledTimes(1));

    await userEvent.clear(screen.getByLabelText(/analytics month/i));
    await userEvent.type(screen.getByLabelText(/analytics month/i), '2026-01');
    await userEvent.clear(screen.getByLabelText(/weekly summary week start/i));
    await userEvent.type(screen.getByLabelText(/weekly summary week start/i), '2026-05-04');
    await userEvent.type(screen.getByLabelText(/weekly summary currency/i), 'usd');
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
          weekStart: '2026-05-04',
          currency: 'USD',
        }),
      ),
    );
  });
});
