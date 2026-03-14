import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AccountsOverview from '@/pages/AccountsOverview';

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
  Badge: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLSpanElement>) => (
    <span {...props}>{children}</span>
  ),
}));
jest.mock('@/components/ui/progress', () => ({
  Progress: ({ value, ...props }: { value?: number } & React.HTMLAttributes<HTMLDivElement>) => (
    <div role="progressbar" aria-valuenow={value} {...props} />
  ),
}));
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  FinancialCardContent: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  FinancialCardDescription: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  FinancialCardHeader: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  FinancialCardTitle: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
}));
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: React.PropsWithChildren & { open?: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/alert-dailog', () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));
jest.mock('@/lib/currency', () => ({
  formatMoney: (amount: number) => `$${Number(amount || 0).toFixed(2)}`,
}));

const listAccountsMock = jest.fn();
const createAccountMock = jest.fn();
const updateAccountMock = jest.fn();
const deleteAccountMock = jest.fn();
const getAccountsOverviewMock = jest.fn();
jest.mock('@/api/accounts', () => ({
  listAccounts: (...args: unknown[]) => listAccountsMock(...args),
  createAccount: (...args: unknown[]) => createAccountMock(...args),
  updateAccount: (...args: unknown[]) => updateAccountMock(...args),
  deleteAccount: (...args: unknown[]) => deleteAccountMock(...args),
  getAccountsOverview: (...args: unknown[]) => getAccountsOverviewMock(...args),
}));

const sampleAccount = {
  id: 1,
  name: 'Main Checking',
  account_type: 'BANK',
  institution: 'Chase',
  balance: 5000,
  currency: 'USD',
  color: '#3B82F6',
  active: true,
  created_at: '2025-01-01T00:00:00',
};

const sampleOverview = {
  total_balance: 15000,
  net_worth: 13000,
  total_assets: 15000,
  total_liabilities: 2000,
  account_count: 2,
  type_breakdown: [
    {
      type: 'BANK',
      total: 13000,
      count: 1,
      accounts: [sampleAccount],
    },
    {
      type: 'CREDIT',
      total: 2000,
      count: 1,
      accounts: [{
        ...sampleAccount,
        id: 2,
        name: 'Visa Card',
        account_type: 'CREDIT',
        balance: 2000,
        color: '#EF4444',
      }],
    },
  ],
};

describe('AccountsOverview integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listAccountsMock.mockResolvedValue([sampleAccount]);
    getAccountsOverviewMock.mockResolvedValue(sampleOverview);
    deleteAccountMock.mockResolvedValue({ message: 'deleted' });
  });

  it('renders accounts list with balance', async () => {
    render(<AccountsOverview />);
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalled());

    expect(await screen.findByText('Main Checking')).toBeInTheDocument();
    expect(screen.getByText('$5000.00')).toBeInTheDocument();
  });

  it('shows empty state when no accounts', async () => {
    listAccountsMock.mockResolvedValue([]);
    getAccountsOverviewMock.mockResolvedValue({
      total_balance: 0,
      net_worth: 0,
      total_assets: 0,
      total_liabilities: 0,
      account_count: 0,
      type_breakdown: [],
    });
    render(<AccountsOverview />);
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalled());

    expect(await screen.findByText(/no accounts yet/i)).toBeInTheDocument();
    expect(screen.getByText(/add your first account/i)).toBeInTheDocument();
  });

  it('shows net worth and summary stats', async () => {
    render(<AccountsOverview />);
    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());

    // Net worth
    expect(await screen.findByText('$13000.00')).toBeInTheDocument();
    // Total assets
    expect(screen.getByText('$15000.00')).toBeInTheDocument();
    // Total liabilities
    expect(screen.getByText('$2000.00')).toBeInTheDocument();
  });

  it('shows type breakdown chart', async () => {
    render(<AccountsOverview />);
    await waitFor(() => expect(getAccountsOverviewMock).toHaveBeenCalled());

    // Progress bars in breakdown
    const progressBars = await screen.findAllByRole('progressbar');
    expect(progressBars.length).toBeGreaterThan(0);
  });

  it('deletes an account when confirmed', async () => {
    listAccountsMock.mockResolvedValue([sampleAccount]);
    render(<AccountsOverview />);
    await waitFor(() => expect(listAccountsMock).toHaveBeenCalled());
    await screen.findByText('Main Checking');

    // Click the delete confirmation button
    const deleteButtons = screen.getAllByText('Delete');
    await userEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => expect(deleteAccountMock).toHaveBeenCalledWith(1));
    expect(toastMock).toHaveBeenCalledWith({ title: 'Account deleted' });
  });
});
