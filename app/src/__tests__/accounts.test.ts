/**
 * Tests for the accounts API module.
 * Validates typed API calls for multi-account financial dashboard.
 */

// Mock the api client
const mockApi = jest.fn();
jest.mock('@/api/client', () => ({
  api: (...args: unknown[]) => mockApi(...args),
  baseURL: 'http://localhost:8000',
}));

import {
  listAccounts,
  getAccount,
  createAccount,
  updateAccount,
  deleteAccount,
  getAccountsOverview,
} from '@/api/accounts';

describe('Accounts API', () => {
  beforeEach(() => {
    mockApi.mockReset();
  });

  it('listAccounts calls GET /accounts', async () => {
    const data = [{ id: 1, name: 'Checking', account_type: 'BANK', balance: 1000 }];
    mockApi.mockResolvedValue(data);
    const result = await listAccounts();
    expect(mockApi).toHaveBeenCalledWith('/accounts');
    expect(result).toEqual(data);
  });

  it('getAccount calls GET /accounts/:id', async () => {
    const data = { id: 42, name: 'Savings' };
    mockApi.mockResolvedValue(data);
    const result = await getAccount(42);
    expect(mockApi).toHaveBeenCalledWith('/accounts/42');
    expect(result).toEqual(data);
  });

  it('createAccount calls POST /accounts', async () => {
    const payload = { name: 'New Acct', account_type: 'BANK' as const, balance: 500 };
    const response = { id: 1, ...payload };
    mockApi.mockResolvedValue(response);
    const result = await createAccount(payload);
    expect(mockApi).toHaveBeenCalledWith('/accounts', { method: 'POST', body: payload });
    expect(result.id).toBe(1);
  });

  it('updateAccount calls PATCH /accounts/:id', async () => {
    const patch = { name: 'Updated' };
    mockApi.mockResolvedValue({ id: 1, name: 'Updated' });
    const result = await updateAccount(1, patch);
    expect(mockApi).toHaveBeenCalledWith('/accounts/1', { method: 'PATCH', body: patch });
    expect(result.name).toBe('Updated');
  });

  it('deleteAccount calls DELETE /accounts/:id', async () => {
    mockApi.mockResolvedValue({ message: 'account deactivated' });
    const result = await deleteAccount(5);
    expect(mockApi).toHaveBeenCalledWith('/accounts/5', { method: 'DELETE' });
    expect(result.message).toBe('account deactivated');
  });

  it('getAccountsOverview calls GET /accounts/overview', async () => {
    const overview = {
      total_accounts: 3,
      total_assets: 15000,
      total_liabilities: 2000,
      net_worth: 13000,
      by_type: { BANK: { count: 2, total_balance: 15000 } },
      by_currency: { USD: 15000 },
      accounts: [],
      recent_transactions: [],
    };
    mockApi.mockResolvedValue(overview);
    const result = await getAccountsOverview();
    expect(mockApi).toHaveBeenCalledWith('/accounts/overview');
    expect(result.net_worth).toBe(13000);
    expect(result.total_accounts).toBe(3);
  });
});
