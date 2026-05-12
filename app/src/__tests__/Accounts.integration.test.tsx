import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Accounts } from '@/pages/Accounts';

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

const getAccountsOverviewMock = jest.fn();
const createAccountMock = jest.fn();
jest.mock('@/api/accounts', () => ({
  getAccountsOverview: (...args: unknown[]) => getAccountsOverviewMock(...args),
  createAccount: (...args: unknown[]) => createAccountMock(...args),
}));

describe('Accounts integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getAccountsOverviewMock.mockResolvedValue({
      period: { month: '2026-05' },
      summary: {
        account_count: 2,
        assets: 7000,
        liabilities: 300,
        net_worth: 6700,
      },
      accounts: [
        {
          id: 1,
          name: 'Main Checking',
          account_type: 'CHECKING',
          balance: 2000,
          currency: 'USD',
          institution: 'Acme Bank',
          active: true,
          monthly_income: 3000,
          monthly_expenses: 120,
          monthly_net_flow: 2880,
          transaction_count: 2,
        },
      ],
      by_type: [{ account_type: 'CHECKING', count: 1, balance: 2000 }],
      by_currency: [{ currency: 'USD', assets: 7000, liabilities: 300, net_worth: 6700 }],
      recent_transactions: [
        {
          id: 10,
          account_id: 1,
          account_name: 'Main Checking',
          description: 'Groceries',
          amount: 120,
          currency: 'USD',
          date: '2026-05-04',
          type: 'EXPENSE',
        },
      ],
    });
    createAccountMock.mockResolvedValue({ id: 3 });
  });

  it('renders account overview data', async () => {
    render(<Accounts />);
    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());

    expect(screen.getByRole('heading', { name: /accounts/i })).toBeInTheDocument();
    expect(screen.getAllByText(/main checking/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/acme bank/i)).toBeInTheDocument();
    expect(screen.getByText(/groceries/i)).toBeInTheDocument();
    expect(screen.getByText(/currency groups/i)).toBeInTheDocument();
  });

  it('creates an account and reloads overview', async () => {
    const user = userEvent.setup();
    render(<Accounts />);
    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalledTimes(1));

    await user.type(screen.getByLabelText(/account name/i), 'Savings');
    await user.selectOptions(screen.getByLabelText(/account type/i), 'SAVINGS');
    await user.clear(screen.getByLabelText(/account balance/i));
    await user.type(screen.getByLabelText(/account balance/i), '1500');
    await user.clear(screen.getByLabelText(/account currency/i));
    await user.type(screen.getByLabelText(/account currency/i), 'usd');
    await user.type(screen.getByLabelText(/account institution/i), 'Credit Union');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() =>
      expect(createAccountMock).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Savings',
          account_type: 'SAVINGS',
          balance: 1500,
          currency: 'USD',
          institution: 'Credit Union',
        }),
      ),
    );
    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalledTimes(2));
  });
});
