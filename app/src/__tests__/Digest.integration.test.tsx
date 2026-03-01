import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import Digest from '@/pages/Digest';

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
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}));

jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/lib/currency', () => ({
  formatMoney: (v: number) => `$${v.toFixed(2)}`,
}));

const mockDigest = {
  period: { start: '2025-02-24', end: '2025-03-02' },
  summary: { total_income: 1000, total_expenses: 500, net_flow: 500 },
  category_breakdown: [
    { category_id: 1, category_name: 'Food', total: 300 },
    { category_id: 2, category_name: 'Transport', total: 200 },
  ],
  trends: {
    spending_change_pct: -10,
    direction: 'down' as const,
    current_week_total: 500,
    previous_week_total: 555.56,
  },
  upcoming_bills: [],
  upcoming_bills_total: 0,
  generated_at: '2025-03-03',
};

jest.mock('@/api/digest', () => ({
  getWeeklyDigest: jest.fn().mockResolvedValue(mockDigest),
  sendWeeklyDigest: jest.fn().mockResolvedValue({ digest: mockDigest, delivery: { email: 'sent' } }),
}));

describe('Digest page', () => {
  it('renders weekly digest with summary data', async () => {
    render(<Digest />);
    await waitFor(() => {
      expect(screen.getByText('Weekly Digest')).toBeInTheDocument();
    });
    expect(screen.getByText('$1000.00')).toBeInTheDocument();
    expect(screen.getByText('$500.00')).toBeInTheDocument();
    expect(screen.getByText('Food')).toBeInTheDocument();
    expect(screen.getByText('Transport')).toBeInTheDocument();
  });

  it('shows trend direction', async () => {
    render(<Digest />);
    await waitFor(() => {
      expect(screen.getByText(/down/i)).toBeInTheDocument();
    });
  });
});
