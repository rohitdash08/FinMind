import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import Accounts from '@/pages/Accounts';

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

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
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectValue: () => <span />,
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
jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <span {...props}>{children}</span>
  ),
}));
jest.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

const overviewMock = jest.fn();

jest.mock('@/api/accounts', () => ({
  getAccountsOverview: (...args: unknown[]) => overviewMock(...args),
  createAccount: jest.fn(),
  updateAccount: jest.fn(),
  deleteAccount: jest.fn(),
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

describe('Accounts page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders empty state when no accounts exist', async () => {
    overviewMock.mockResolvedValue({
      accounts: [],
      total_balance: 0,
      account_count: 0,
      recent_expenses: [],
      upcoming_bills: [],
    });
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText(/no financial accounts yet/i)).toBeInTheDocument();
    });
  });

  it('renders accounts list with balances', async () => {
    overviewMock.mockResolvedValue({
      accounts: [
        {
          id: 1,
          name: 'Main Checking',
          account_type: 'CHECKING',
          balance: 5000,
          currency: 'USD',
          institution: 'Chase Bank',
          active: true,
        },
        {
          id: 2,
          name: 'Savings',
          account_type: 'SAVINGS',
          balance: 10000,
          currency: 'USD',
          institution: null,
          active: true,
        },
      ],
      total_balance: 15000,
      account_count: 2,
      recent_expenses: [],
      upcoming_bills: [],
    });
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText('Main Checking')).toBeInTheDocument();
    });
    expect(screen.getByText('Savings')).toBeInTheDocument();
    expect(screen.getByText('Chase Bank')).toBeInTheDocument();
    expect(screen.getByText('$15,000.00')).toBeInTheDocument();
  });

  it('shows Add Account button', async () => {
    overviewMock.mockResolvedValue({
      accounts: [],
      total_balance: 0,
      account_count: 0,
      recent_expenses: [],
      upcoming_bills: [],
    });
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText(/add account/i)).toBeInTheDocument();
    });
  });

  it('renders recent expenses and upcoming bills', async () => {
    overviewMock.mockResolvedValue({
      accounts: [
        { id: 1, name: 'Checking', account_type: 'CHECKING', balance: 1000, currency: 'USD', institution: null, active: true },
      ],
      total_balance: 1000,
      account_count: 1,
      recent_expenses: [
        { id: 1, amount: 50, currency: 'USD', description: 'Groceries', date: '2026-03-20' },
      ],
      upcoming_bills: [
        { id: 1, name: 'Internet', amount: 49.99, currency: 'USD', next_due_date: '2026-04-01' },
      ],
    });
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText('Groceries')).toBeInTheDocument();
    });
    expect(screen.getByText('Internet')).toBeInTheDocument();
  });
});
