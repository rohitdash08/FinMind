import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AccountsOverview } from '@/pages/AccountsOverview';

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const listAccountsMock = jest.fn();
const getAccountsOverviewMock = jest.fn();
const createAccountMock = jest.fn();
const updateAccountMock = jest.fn();
const deleteAccountMock = jest.fn();

jest.mock('@/api/accounts', () => ({
  listAccounts: (...args: unknown[]) => listAccountsMock(...args),
  getAccountsOverview: (...args: unknown[]) => getAccountsOverviewMock(...args),
  createAccount: (...args: unknown[]) => createAccountMock(...args),
  updateAccount: (...args: unknown[]) => updateAccountMock(...args),
  deleteAccount: (...args: unknown[]) => deleteAccountMock(...args),
}));

const mockAccounts = [
  {
    id: 1,
    name: 'Chase Checking',
    account_type: 'CHECKING',
    institution: 'Chase',
    balance: 5000,
    currency: 'USD',
    is_active: true,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  },
  {
    id: 2,
    name: 'Vanguard 401k',
    account_type: 'INVESTMENT',
    institution: 'Vanguard',
    balance: 50000,
    currency: 'USD',
    is_active: true,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  },
];

const mockOverview = {
  total_accounts: 2,
  total_balance: 55000,
  by_type: [
    { type: 'CHECKING', count: 1, total_balance: 5000, accounts: [mockAccounts[0]] },
    { type: 'INVESTMENT', count: 1, total_balance: 50000, accounts: [mockAccounts[1]] },
  ],
  by_currency: [{ currency: 'USD', balance: 55000 }],
  by_institution: [
    { institution: 'Chase', count: 1, total_balance: 5000 },
    { institution: 'Vanguard', count: 1, total_balance: 50000 },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/accounts']}>
      <Routes>
        <Route path="/accounts" element={<AccountsOverview />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AccountsOverview integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders accounts overview with accounts and summary data', async () => {
    listAccountsMock.mockResolvedValue(mockAccounts);
    getAccountsOverviewMock.mockResolvedValue(mockOverview);

    renderPage();

    await waitFor(() => expect(listAccountsMock).toHaveBeenCalled());
    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());

    expect(screen.getByText(/accounts overview/i)).toBeInTheDocument();
    expect(screen.getByText(/total net worth/i)).toBeInTheDocument();
    expect(screen.getByText(/chase checking/i)).toBeInTheDocument();
    expect(screen.getByText(/vanguard 401k/i)).toBeInTheDocument();
    expect(screen.getByText(/by account type/i)).toBeInTheDocument();
    expect(screen.getByText(/by institution/i)).toBeInTheDocument();
  });

  it('renders empty state when no accounts exist', async () => {
    listAccountsMock.mockResolvedValue([]);
    getAccountsOverviewMock.mockResolvedValue({
      total_accounts: 0,
      total_balance: 0,
      by_type: [],
      by_currency: [],
      by_institution: [],
    });

    renderPage();

    await waitFor(() => expect(listAccountsMock).toHaveBeenCalled());

    expect(screen.getByText(/no accounts yet/i)).toBeInTheDocument();
    expect(screen.getByText(/add your first account/i)).toBeInTheDocument();
  });

  it('opens add account dialog and submits', async () => {
    const user = userEvent.setup();
    listAccountsMock.mockResolvedValue([]);
    getAccountsOverviewMock.mockResolvedValue({
      total_accounts: 0,
      total_balance: 0,
      by_type: [],
      by_currency: [],
      by_institution: [],
    });
    createAccountMock.mockResolvedValue({ id: 1, name: 'New Account', account_type: 'CHECKING', balance: 0 });

    renderPage();

    await waitFor(() => expect(listAccountsMock).toHaveBeenCalled());

    // Click "Add Account" button in the header
    const addButtons = screen.getAllByRole('button', { name: /add account/i });
    await user.click(addButtons[0]);

    // Dialog should be open
    expect(screen.getByText(/add account/i)).toBeInTheDocument();

    // Fill form
    await user.clear(screen.getByLabelText(/name/i));
    await user.type(screen.getByLabelText(/name/i), 'New Checking');

    // Submit
    await user.click(screen.getByRole('button', { name: /add account$/i }));

    await waitFor(() => expect(createAccountMock).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'New Checking', account_type: 'CHECKING' }),
    ));
  });

  it('shows error state on API failure', async () => {
    listAccountsMock.mockRejectedValue(new Error('Network error'));
    getAccountsOverviewMock.mockRejectedValue(new Error('Network error'));

    renderPage();

    await waitFor(() => expect(screen.getByText(/network error/i)).toBeInTheDocument());
  });
});
