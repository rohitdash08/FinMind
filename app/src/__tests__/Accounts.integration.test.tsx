import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import Accounts from '@/pages/Accounts';

const toastMock = jest.fn();
jest.mock('@/components/ui/use-toast', () => ({
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
  Dialog: ({ children, open }: React.PropsWithChildren & { open?: boolean }) => (
    <div data-testid="dialog" data-open={open}>{children}</div>
  ),
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
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

const emptyOverview = {
  accounts: [],
  total_balance: 0,
  totals_by_currency: {},
  account_count: 0,
  recent_expenses: [],
  upcoming_bills: [],
};

describe('Accounts page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders empty state when no accounts exist', async () => {
    overviewMock.mockResolvedValue(emptyOverview);
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
          created_at: '2026-01-01T00:00:00',
        },
        {
          id: 2,
          name: 'Savings',
          account_type: 'SAVINGS',
          balance: 10000,
          currency: 'USD',
          institution: null,
          active: true,
          created_at: '2026-01-01T00:00:00',
        },
      ],
      total_balance: 15000,
      totals_by_currency: { USD: 15000 },
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
    // Verify currency-aware formatting
    expect(screen.getByText('$15,000.00')).toBeInTheDocument();
  });

  it('shows Add Account button', async () => {
    overviewMock.mockResolvedValue(emptyOverview);
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText(/add account/i)).toBeInTheDocument();
    });
  });

  it('renders recent expenses and upcoming bills', async () => {
    overviewMock.mockResolvedValue({
      accounts: [
        { id: 1, name: 'Checking', account_type: 'CHECKING', balance: 1000, currency: 'USD', institution: null, active: true, created_at: null },
      ],
      total_balance: 1000,
      totals_by_currency: { USD: 1000 },
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

  it('renders error state on fetch failure', async () => {
    overviewMock.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load accounts/i)).toBeInTheDocument();
    });
  });

  it('renders multi-currency totals correctly', async () => {
    overviewMock.mockResolvedValue({
      accounts: [
        { id: 1, name: 'USD', account_type: 'CHECKING', balance: 1000, currency: 'USD', institution: null, active: true, created_at: null },
        { id: 2, name: 'EUR', account_type: 'SAVINGS', balance: 2000, currency: 'EUR', institution: null, active: true, created_at: null },
      ],
      total_balance: 3000,
      totals_by_currency: { USD: 1000, EUR: 2000 },
      account_count: 2,
      recent_expenses: [],
      upcoming_bills: [],
    });
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText('USD')).toBeInTheDocument();
    });
    // Both currency totals should be displayed
    expect(screen.getByText('EUR')).toBeInTheDocument();
  });

  it('shows delete confirmation dialog', async () => {
    overviewMock.mockResolvedValue({
      accounts: [
        { id: 1, name: 'Test Account', account_type: 'CHECKING', balance: 100, currency: 'USD', institution: null, active: true, created_at: null },
      ],
      total_balance: 100,
      totals_by_currency: { USD: 100 },
      account_count: 1,
      recent_expenses: [],
      upcoming_bills: [],
    });
    renderWithProviders(<Accounts />);

    await waitFor(() => {
      expect(screen.getByText('Test Account')).toBeInTheDocument();
    });
    // Delete confirmation dialog title should be present in the DOM
    expect(screen.getByText('Delete Account')).toBeInTheDocument();
  });
});
