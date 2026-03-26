import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { Accounts } from '../pages/Accounts';

// Mock API modules
jest.mock('../api/accounts', () => ({
  listAccounts: jest.fn(),
  createAccount: jest.fn(),
  updateAccount: jest.fn(),
  deleteAccount: jest.fn(),
  getAccountsOverview: jest.fn(),
  getAccountTransactions: jest.fn(),
}));

jest.mock('../lib/auth', () => ({
  getToken: () => 'mock-token',
  getRefreshToken: () => 'mock-refresh',
  clearToken: jest.fn(),
  clearRefreshToken: jest.fn(),
  setToken: jest.fn(),
  getCurrency: () => 'INR',
}));

const mockAccounts = [
  {
    id: 1,
    name: 'HDFC Checking',
    account_type: 'CHECKING',
    institution: 'HDFC Bank',
    balance: 25000.5,
    currency: 'INR',
    is_active: true,
    notes: null,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  },
  {
    id: 2,
    name: 'SBI Savings',
    account_type: 'SAVINGS',
    institution: 'SBI',
    balance: 100000,
    currency: 'INR',
    is_active: true,
    notes: null,
    created_at: '2026-01-02T00:00:00',
    updated_at: '2026-01-02T00:00:00',
  },
  {
    id: 3,
    name: 'Visa Gold',
    account_type: 'CREDIT_CARD',
    institution: 'ICICI',
    balance: 15000,
    currency: 'INR',
    is_active: true,
    notes: null,
    created_at: '2026-01-03T00:00:00',
    updated_at: '2026-01-03T00:00:00',
  },
];

const mockOverview = {
  period: { month: '2026-03' },
  net_worth: 110000.5,
  total_assets: 125000.5,
  total_liabilities: 15000,
  aggregate: {
    monthly_income: 50000,
    monthly_expenses: 20000,
    monthly_net: 30000,
  },
  accounts: mockAccounts.map((a) => ({
    ...a,
    monthly_income: a.account_type === 'CHECKING' ? 50000 : 0,
    monthly_expenses: a.account_type === 'CHECKING' ? 12000 : a.account_type === 'CREDIT_CARD' ? 8000 : 0,
    monthly_net: a.account_type === 'CHECKING' ? 38000 : a.account_type === 'CREDIT_CARD' ? -8000 : 0,
    transaction_count: a.account_type === 'CHECKING' ? 15 : a.account_type === 'CREDIT_CARD' ? 5 : 0,
  })),
  account_count: 3,
  recent_transactions: [
    {
      id: 101,
      description: 'Salary',
      amount: 50000,
      date: '2026-03-01',
      type: 'INCOME',
      currency: 'INR',
      account_id: 1,
    },
    {
      id: 102,
      description: 'Groceries',
      amount: 2500,
      date: '2026-03-15',
      type: 'EXPENSE',
      currency: 'INR',
      account_id: 1,
    },
  ],
};

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  const accountsApi = require('../api/accounts');
  accountsApi.listAccounts.mockResolvedValue(mockAccounts);
  accountsApi.getAccountsOverview.mockResolvedValue(mockOverview);
});

describe('Accounts page', () => {
  it('renders page title', async () => {
    renderWithProviders(<Accounts />);
    expect(screen.getByText('Financial Accounts')).toBeInTheDocument();
  });

  it('displays summary cards after loading', async () => {
    renderWithProviders(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Net Worth')).toBeInTheDocument();
    });
    expect(screen.getByText('Total Assets')).toBeInTheDocument();
    expect(screen.getByText('Total Liabilities')).toBeInTheDocument();
    expect(screen.getByText('Monthly Net')).toBeInTheDocument();
  });

  it('groups accounts by type', async () => {
    renderWithProviders(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Checking Accounts')).toBeInTheDocument();
    });
    expect(screen.getByText('Savings Accounts')).toBeInTheDocument();
    expect(screen.getByText('Credit Card Accounts')).toBeInTheDocument();
  });

  it('shows account names and institutions', async () => {
    renderWithProviders(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('HDFC Checking')).toBeInTheDocument();
    });
    expect(screen.getByText('SBI Savings')).toBeInTheDocument();
    expect(screen.getByText('Visa Gold')).toBeInTheDocument();
    expect(screen.getByText('HDFC Bank')).toBeInTheDocument();
  });

  it('displays recent transactions', async () => {
    renderWithProviders(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Salary')).toBeInTheDocument();
    });
    expect(screen.getByText('Groceries')).toBeInTheDocument();
  });

  it('shows add account button', async () => {
    renderWithProviders(<Accounts />);
    expect(screen.getByText('Add Account')).toBeInTheDocument();
  });

  it('shows empty state when no accounts', async () => {
    const accountsApi = require('../api/accounts');
    accountsApi.listAccounts.mockResolvedValue([]);
    accountsApi.getAccountsOverview.mockResolvedValue({
      ...mockOverview,
      accounts: [],
      account_count: 0,
      net_worth: 0,
      total_assets: 0,
      total_liabilities: 0,
    });
    renderWithProviders(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText(/No accounts yet/)).toBeInTheDocument();
    });
  });

  it('handles API errors gracefully', async () => {
    const accountsApi = require('../api/accounts');
    accountsApi.listAccounts.mockRejectedValue(new Error('Network error'));
    accountsApi.getAccountsOverview.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });
});
