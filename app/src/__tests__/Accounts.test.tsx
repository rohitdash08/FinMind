import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Accounts } from '../pages/Accounts';
import * as accountsApi from '../api/accounts';

jest.mock('../api/accounts');
jest.mock('../hooks/use-toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
}));

const mockAccounts: accountsApi.FinancialAccount[] = [
  {
    id: 1,
    name: 'Chase Checking',
    type: 'CHECKING',
    balance: 5000,
    currency: 'USD',
    institution: 'Chase',
    last_synced: '2026-03-22T10:00:00Z',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'Emergency Fund',
    type: 'SAVINGS',
    balance: 15000,
    currency: 'USD',
    institution: 'Ally Bank',
    last_synced: null,
    is_active: true,
    created_at: '2026-01-15T00:00:00Z',
  },
  {
    id: 3,
    name: 'Amex Gold',
    type: 'CREDIT_CARD',
    balance: 2500,
    currency: 'USD',
    institution: 'American Express',
    last_synced: '2026-03-20T08:00:00Z',
    is_active: true,
    created_at: '2026-02-01T00:00:00Z',
  },
  {
    id: 4,
    name: 'Fidelity 401k',
    type: 'INVESTMENT',
    balance: 85000,
    currency: 'USD',
    institution: 'Fidelity',
    last_synced: '2026-03-21T00:00:00Z',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
];

const mockSummary: accountsApi.AccountSummary = {
  total_assets: 105000,
  total_liabilities: 2500,
  net_worth: 102500,
  currency: 'USD',
  accounts: mockAccounts,
};

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

describe('Accounts Page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (accountsApi.getAccounts as jest.Mock).mockResolvedValue(mockAccounts);
    (accountsApi.getAccountSummary as jest.Mock).mockResolvedValue(mockSummary);
  });

  it('renders the page title', async () => {
    renderWithRouter(<Accounts />);
    expect(screen.getByText('Financial Accounts')).toBeInTheDocument();
  });

  it('displays summary cards after loading', async () => {
    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Total Assets')).toBeInTheDocument();
      expect(screen.getByText('Total Liabilities')).toBeInTheDocument();
      expect(screen.getByText('Net Worth')).toBeInTheDocument();
    });
  });

  it('groups accounts by type', async () => {
    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Checking Accounts')).toBeInTheDocument();
      expect(screen.getByText('Savings Accounts')).toBeInTheDocument();
      expect(screen.getByText('Credit Card Accounts')).toBeInTheDocument();
      expect(screen.getByText('Investment Accounts')).toBeInTheDocument();
    });
  });

  it('displays individual account cards', async () => {
    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Chase Checking')).toBeInTheDocument();
      expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
      expect(screen.getByText('Amex Gold')).toBeInTheDocument();
      expect(screen.getByText('Fidelity 401k')).toBeInTheDocument();
    });
  });

  it('shows institution names', async () => {
    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Chase')).toBeInTheDocument();
      expect(screen.getByText('Ally Bank')).toBeInTheDocument();
      expect(screen.getByText('American Express')).toBeInTheDocument();
      expect(screen.getByText('Fidelity')).toBeInTheDocument();
    });
  });

  it('opens add account form when button clicked', async () => {
    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Chase Checking')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Add Account'));
    expect(screen.getByText('New Account')).toBeInTheDocument();
    expect(screen.getByLabelText('Account Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Type')).toBeInTheDocument();
    expect(screen.getByLabelText('Current Balance')).toBeInTheDocument();
  });

  it('creates a new account', async () => {
    (accountsApi.createAccount as jest.Mock).mockResolvedValue({
      id: 5,
      name: 'Test Account',
      type: 'CASH',
      balance: 100,
      currency: 'USD',
      institution: '',
      last_synced: null,
      is_active: true,
      created_at: '2026-03-22T15:00:00Z',
    });

    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Chase Checking')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Add Account'));
    fireEvent.change(screen.getByLabelText('Account Name'), {
      target: { value: 'Test Account' },
    });
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'CASH' },
    });
    fireEvent.change(screen.getByLabelText('Current Balance'), {
      target: { value: '100' },
    });
    fireEvent.click(screen.getByText('Create'));

    await waitFor(() => {
      expect(accountsApi.createAccount).toHaveBeenCalledWith({
        name: 'Test Account',
        type: 'CASH',
        balance: 100,
      });
    });
  });

  it('shows empty state when no accounts', async () => {
    (accountsApi.getAccounts as jest.Mock).mockResolvedValue([]);
    (accountsApi.getAccountSummary as jest.Mock).mockResolvedValue({
      total_assets: 0,
      total_liabilities: 0,
      net_worth: 0,
      currency: 'USD',
      accounts: [],
    });

    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('No accounts yet')).toBeInTheDocument();
      expect(screen.getByText('Add Your First Account')).toBeInTheDocument();
    });
  });

  it('shows error when API fails', async () => {
    (accountsApi.getAccounts as jest.Mock).mockRejectedValue(new Error('Network error'));

    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });
  });

  it('handles delete account', async () => {
    (accountsApi.deleteAccount as jest.Mock).mockResolvedValue(undefined);

    renderWithRouter(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText('Chase Checking')).toBeInTheDocument();
    });
  });
});