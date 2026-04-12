import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Digest } from '@/pages/Digest';

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

const getWeeklyDigestMock = jest.fn();
jest.mock('@/api/digest', () => ({
  getWeeklyDigest: (...args: unknown[]) => getWeeklyDigestMock(...args),
}));

describe('Digest integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getWeeklyDigestMock.mockResolvedValue({
      week: '2026-W15',
      total_income: 5000,
      total_expenses: 3200,
      net_flow: 1800,
      tips: ['Cut coffee spending by 15%.', 'Set a mid-week checkpoint.'],
      analytics: {
        week_over_week_change_pct: -8.5,
        current_week_expenses: 3200,
        previous_week_expenses: 3496.5,
        top_categories: [{ category_id: 'food', amount: 1200 }],
      },
      persona: 'Balanced coach',
      method: 'heuristic',
      warnings: [],
    });
  });

  it('loads and renders weekly digest data', async () => {
    render(<Digest />);
    await waitFor(() => expect(getWeeklyDigestMock).toHaveBeenCalled());
    expect(screen.getByText(/weekly digest/i)).toBeInTheDocument();
    expect(screen.getByText(/total income/i)).toBeInTheDocument();
    expect(screen.getByText(/total expenses/i)).toBeInTheDocument();
    expect(screen.getByText(/net flow/i)).toBeInTheDocument();
    expect(screen.getByText(/cut coffee spending/i)).toBeInTheDocument();
  });

  it('calls API with week/persona/key when Load Digest is clicked', async () => {
    render(<Digest />);
    await waitFor(() => expect(getWeeklyDigestMock).toHaveBeenCalledTimes(1));

    await userEvent.clear(screen.getByLabelText(/digest week/i));
    await userEvent.type(screen.getByLabelText(/digest week/i), '2026-W10');
    await userEvent.selectOptions(screen.getByLabelText(/digest persona/i), 'Debt-focused planner');
    await userEvent.type(screen.getByLabelText(/gemini api key/i), 'test-key');
    await userEvent.click(screen.getByRole('button', { name: /load digest/i }));

    await waitFor(() =>
      expect(getWeeklyDigestMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          week: '2026-W10',
          persona: 'Debt-focused planner',
          geminiApiKey: 'test-key',
        }),
      ),
    );
  });

  it('displays error message on API failure', async () => {
    getWeeklyDigestMock.mockRejectedValueOnce(new Error('Network error'));
    render(<Digest />);
    await waitFor(() => expect(screen.getByText(/network error/i)).toBeInTheDocument());
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Failed to load digest' }),
    );
  });
});
