import {
  listAccounts,
  getAccount,
  createAccount,
  updateAccount,
  deleteAccount,
  getAccountSummary,
  depositToAccount,
  withdrawFromAccount,
  transferBetweenAccounts,
  getAccountTransactions,
  type Account,
  type AccountSummary,
  type AccountTransaction,
} from '../api/accounts';
import * as client from '../api/client';

// Mock the API client
jest.mock('../api/client', () => ({
  api: jest.fn(),
  baseURL: 'http://localhost:3000/api',
}));

const mockAccount: Account = {
  id: 1,
  name: 'Main Checking',
  type: 'CHECKING',
  balance: 5000,
  currency: 'USD',
  institution: 'Bank of America',
  account_number_last4: '1234',
  active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
};

const mockSummary: AccountSummary = {
  total_assets: 15000,
  total_liabilities: 2000,
  net_worth: 13000,
  accounts_by_type: {
    CHECKING: { count: 2, total: 8000 },
    SAVINGS: { count: 1, total: 5000 },
    CREDIT_CARD: { count: 1, total: -2000 },
    INVESTMENT: { count: 1, total: 4000 },
    CASH: { count: 0, total: 0 },
    OTHER: { count: 0, total: 0 },
  },
  currency: 'USD',
};

const mockTransaction: AccountTransaction = {
  id: 1,
  account_id: 1,
  amount: 100,
  type: 'DEPOSIT',
  description: 'Paycheck',
  date: '2026-03-10T00:00:00Z',
  balance_after: 5100,
};

describe('accounts API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('listAccounts', () => {
    it('fetches all accounts', async () => {
      const mockAccounts = [mockAccount];
      (client.api as jest.Mock).mockResolvedValueOnce(mockAccounts);

      const result = await listAccounts();

      expect(client.api).toHaveBeenCalledWith('/accounts');
      expect(result).toEqual(mockAccounts);
    });

    it('filters by account type', async () => {
      const mockAccounts = [mockAccount];
      (client.api as jest.Mock).mockResolvedValueOnce(mockAccounts);

      const result = await listAccounts({ type: 'CHECKING' });

      expect(client.api).toHaveBeenCalledWith('/accounts?type=CHECKING');
      expect(result).toEqual(mockAccounts);
    });

    it('filters by active status', async () => {
      const mockAccounts = [mockAccount];
      (client.api as jest.Mock).mockResolvedValueOnce(mockAccounts);

      const result = await listAccounts({ active: true });

      expect(client.api).toHaveBeenCalledWith('/accounts?active=true');
      expect(result).toEqual(mockAccounts);
    });
  });

  describe('getAccount', () => {
    it('fetches a single account by ID', async () => {
      (client.api as jest.Mock).mockResolvedValueOnce(mockAccount);

      const result = await getAccount(1);

      expect(client.api).toHaveBeenCalledWith('/accounts/1');
      expect(result).toEqual(mockAccount);
    });
  });

  describe('createAccount', () => {
    it('creates a new account', async () => {
      const payload = {
        name: 'Savings Account',
        type: 'SAVINGS' as const,
        balance: 1000,
        institution: 'Chase',
      };
      const created = { ...mockAccount, ...payload, id: 2 };
      (client.api as jest.Mock).mockResolvedValueOnce(created);

      const result = await createAccount(payload);

      expect(client.api).toHaveBeenCalledWith('/accounts', {
        method: 'POST',
        body: payload,
      });
      expect(result).toEqual(created);
    });

    it('creates a credit card account', async () => {
      const payload = {
        name: 'Visa Card',
        type: 'CREDIT_CARD' as const,
        balance: -500,
        institution: 'Citibank',
        account_number_last4: '5678',
      };
      (client.api as jest.Mock).mockResolvedValueOnce({ ...mockAccount, ...payload });

      const result = await createAccount(payload);

      expect(client.api).toHaveBeenCalledWith('/accounts', {
        method: 'POST',
        body: payload,
      });
    });
  });

  describe('updateAccount', () => {
    it('updates an existing account', async () => {
      const update = { name: 'Updated Checking' };
      const updated = { ...mockAccount, ...update };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await updateAccount(1, update);

      expect(client.api).toHaveBeenCalledWith('/accounts/1', {
        method: 'PATCH',
        body: update,
      });
      expect(result.name).toBe('Updated Checking');
    });

    it('deactivates an account', async () => {
      const update = { active: false };
      const updated = { ...mockAccount, active: false };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await updateAccount(1, update);

      expect(result.active).toBe(false);
    });
  });

  describe('deleteAccount', () => {
    it('deletes an account', async () => {
      const response = { message: 'Account deleted' };
      (client.api as jest.Mock).mockResolvedValueOnce(response);

      const result = await deleteAccount(1);

      expect(client.api).toHaveBeenCalledWith('/accounts/1', {
        method: 'DELETE',
      });
      expect(result).toEqual(response);
    });
  });

  describe('getAccountSummary', () => {
    it('fetches account summary and net worth', async () => {
      (client.api as jest.Mock).mockResolvedValueOnce(mockSummary);

      const result = await getAccountSummary();

      expect(client.api).toHaveBeenCalledWith('/accounts/summary');
      expect(result).toEqual(mockSummary);
      expect(result.net_worth).toBe(13000);
    });

    it('calculates correct account type totals', async () => {
      (client.api as jest.Mock).mockResolvedValueOnce(mockSummary);

      const result = await getAccountSummary();

      expect(result.accounts_by_type.CHECKING.total).toBe(8000);
      expect(result.accounts_by_type.CREDIT_CARD.total).toBe(-2000);
    });
  });

  describe('depositToAccount', () => {
    it('deposits funds to an account', async () => {
      const updated = { ...mockAccount, balance: 5500 };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await depositToAccount(1, 500, 'Paycheck');

      expect(client.api).toHaveBeenCalledWith('/accounts/1/deposit', {
        method: 'POST',
        body: { amount: 500, description: 'Paycheck' },
      });
      expect(result.balance).toBe(5500);
    });

    it('deposits without description', async () => {
      const updated = { ...mockAccount, balance: 5200 };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await depositToAccount(1, 200);

      expect(client.api).toHaveBeenCalledWith('/accounts/1/deposit', {
        method: 'POST',
        body: { amount: 200, description: undefined },
      });
    });
  });

  describe('withdrawFromAccount', () => {
    it('withdraws funds from an account', async () => {
      const updated = { ...mockAccount, balance: 4500 };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await withdrawFromAccount(1, 500, 'ATM withdrawal');

      expect(client.api).toHaveBeenCalledWith('/accounts/1/withdraw', {
        method: 'POST',
        body: { amount: 500, description: 'ATM withdrawal' },
      });
      expect(result.balance).toBe(4500);
    });
  });

  describe('transferBetweenAccounts', () => {
    it('transfers funds between accounts', async () => {
      const fromAccount = { ...mockAccount, balance: 4500 };
      const toAccount = { ...mockAccount, id: 2, balance: 1500 };
      (client.api as jest.Mock).mockResolvedValueOnce({
        from_account: fromAccount,
        to_account: toAccount,
      });

      const result = await transferBetweenAccounts(1, 2, 500, 'Transfer to savings');

      expect(client.api).toHaveBeenCalledWith('/accounts/transfer', {
        method: 'POST',
        body: {
          from_account_id: 1,
          to_account_id: 2,
          amount: 500,
          description: 'Transfer to savings',
        },
      });
      expect(result.from_account.balance).toBe(4500);
      expect(result.to_account.balance).toBe(1500);
    });
  });

  describe('getAccountTransactions', () => {
    it('fetches transaction history', async () => {
      const mockTransactions = [mockTransaction];
      (client.api as jest.Mock).mockResolvedValueOnce(mockTransactions);

      const result = await getAccountTransactions(1);

      expect(client.api).toHaveBeenCalledWith('/accounts/1/transactions');
      expect(result).toEqual(mockTransactions);
    });

    it('filters transactions by date range', async () => {
      const mockTransactions = [mockTransaction];
      (client.api as jest.Mock).mockResolvedValueOnce(mockTransactions);

      const result = await getAccountTransactions(1, {
        from: '2026-01-01',
        to: '2026-03-01',
      });

      expect(client.api).toHaveBeenCalledWith('/accounts/1/transactions?from=2026-01-01&to=2026-03-01');
      expect(result).toEqual(mockTransactions);
    });

    it('limits transaction results', async () => {
      const mockTransactions = [mockTransaction];
      (client.api as jest.Mock).mockResolvedValueOnce(mockTransactions);

      const result = await getAccountTransactions(1, { limit: 10 });

      expect(client.api).toHaveBeenCalledWith('/accounts/1/transactions?limit=10');
    });
  });

  describe('Edge Cases', () => {
    it('handles negative balances (credit cards)', async () => {
      const creditCard = { ...mockAccount, type: 'CREDIT_CARD' as const, balance: -1500 };
      (client.api as jest.Mock).mockResolvedValueOnce(creditCard);

      const result = await getAccount(5);

      expect(result.balance).toBeLessThan(0);
      expect(result.type).toBe('CREDIT_CARD');
    });

    it('handles zero balance accounts', async () => {
      const zeroAccount = { ...mockAccount, balance: 0 };
      (client.api as jest.Mock).mockResolvedValueOnce(zeroAccount);

      const result = await getAccount(99);

      expect(result.balance).toBe(0);
    });

    it('handles inactive accounts', async () => {
      const inactiveAccount = { ...mockAccount, active: false };
      (client.api as jest.Mock).mockResolvedValueOnce(inactiveAccount);

      const result = await getAccount(10);

      expect(result.active).toBe(false);
    });
  });
});
