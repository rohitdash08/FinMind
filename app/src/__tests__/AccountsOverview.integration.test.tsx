import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AccountsOverview } from '@/pages/AccountsOverview';

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const getAccountsOverviewMock = jest.fn();
const createAccountMock = jest.fn();
const updateAccountMock = jest.fn();
const deleteAccountMock = jest.fn();

jest.mock('@/api/accounts', () => ({
  getAccountsOverview: (...args: unknown[]) => getAccountsOverviewMock(...args),
  createAccount: (...args: unknown[]) => createAccountMock(...args),
  updateAccount: (...args: unknown[]) => updateAccountMock(...args),
  deleteAccount: (...args: unknown[]) => deleteAccountMock(...args),
}));

const mockToast = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

const MOCK_OVERVIEW = {
  accounts: [
    {
      id: 1,
      name: 'Main Checking',
      account_type: 'CHECKING',
      balance: 5000.0,
      currency: 'USD',
      active: true,
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    },
    {
      id: 2,
      name: 'Emergency Savings',
      account_type: 'SAVINGS',
      balance: 10000.0,
      currency: 'USD',
      active: true,
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    },
    {
      id: 3,
      name: 'Visa Card',
      account_type: 'CREDIT',
      balance: -2000.0,
      currency: 'USD',
      active: true,
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    },
  ],
  summary: {
    total_accounts: 3,
    total_assets: 15000.0,
    total_liabilities: 2000.0,
    net_worth: 13000.0,
    by_type: {
      CHECKING: 5000.0,
      SAVINGS: 10000.0,
      CREDIT: -2000.0,
    },
  },
};

describe('AccountsOverview integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders summary cards and account list from backend payload', async () => {
    getAccountsOverviewMock.mockResolvedValue(MOCK_OVERVIEW);

    render(
      <MemoryRouter initialEntries={['/accounts']}>
        <Routes>
          <Route path="/accounts" element={<AccountsOverview />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());

    expect(screen.getByText(/accounts overview/i)).toBeInTheDocument();
    expect(screen.getByText(/main checking/i)).toBeInTheDocument();
    expect(screen.getByText(/emergency savings/i)).toBeInTheDocument();
    expect(screen.getByText(/visa card/i)).toBeInTheDocument();
    expect(screen.getByText(/net worth/i)).toBeInTheDocument();
    expect(screen.getByText(/total assets/i)).toBeInTheDocument();
    expect(screen.getByText(/total liabilities/i)).toBeInTheDocument();
  });

  it('shows empty state when no accounts exist', async () => {
    getAccountsOverviewMock.mockResolvedValue({
      accounts: [],
      summary: {
        total_accounts: 0,
        total_assets: 0,
        total_liabilities: 0,
        net_worth: 0,
        by_type: {},
      },
    });

    render(
      <MemoryRouter initialEntries={['/accounts']}>
        <Routes>
          <Route path="/accounts" element={<AccountsOverview />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());
    expect(screen.getByText(/no accounts yet/i)).toBeInTheDocument();
    expect(screen.getByText(/add your first account/i)).toBeInTheDocument();
  });

  it('shows error state on API failure', async () => {
    getAccountsOverviewMock.mockRejectedValue(new Error('Network error'));

    render(
      <MemoryRouter initialEntries={['/accounts']}>
        <Routes>
          <Route path="/accounts" element={<AccountsOverview />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());
    expect(screen.getByText(/network error/i)).toBeInTheDocument();
  });

  it('renders balance by account type breakdown', async () => {
    getAccountsOverviewMock.mockResolvedValue(MOCK_OVERVIEW);

    render(
      <MemoryRouter initialEntries={['/accounts']}>
        <Routes>
          <Route path="/accounts" element={<AccountsOverview />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());
    expect(screen.getByText(/balance by account type/i)).toBeInTheDocument();
    expect(screen.getByText(/checking/i)).toBeInTheDocument();
  });
});
