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
jest.mock('@/api/insights', () => ({
  getBudgetSuggestion: (...args: unknown[]) => getBudgetSuggestionMock(...args),
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
  });

  it('loads and renders insights data', async () => {
    render(<Analytics />);
    await waitFor(() => expect(getBudgetSuggestionMock).toHaveBeenCalled());
    expect(screen.getByText(/live spending analytics/i)).toBeInTheDocument();
    expect(screen.getByText(/suggested budget/i)).toBeInTheDocument();
    expect(screen.getByText(/tip a/i)).toBeInTheDocument();
  });

  it('refreshes insights with month/persona/key controls', async () => {
    render(<Analytics />);
    await waitFor(() => expect(getBudgetSuggestionMock).toHaveBeenCalledTimes(1));

    await userEvent.clear(screen.getByLabelText(/analytics month/i));
    await userEvent.type(screen.getByLabelText(/analytics month/i), '2026-01');
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
  });
});
