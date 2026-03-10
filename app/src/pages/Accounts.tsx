import { useState, useEffect } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Wallet,
  Plus,
  CreditCard,
  PiggyBank,
  TrendingUp,
  TrendingDown,
  Building2,
  DollarSign,
  Edit,
  Trash2,
  ArrowUpCircle,
  ArrowDownCircle,
  ArrowRightLeft,
} from 'lucide-react';
import {
  listAccounts,
  getAccountSummary,
  createAccount,
  updateAccount,
  deleteAccount,
  depositToAccount,
  withdrawFromAccount,
  transferBetweenAccounts,
  type Account,
  type AccountType,
  type AccountSummary,
} from '@/api/accounts';

const ACCOUNT_TYPE_ICONS: Record<AccountType, typeof Wallet> = {
  CHECKING: Wallet,
  SAVINGS: PiggyBank,
  CREDIT_CARD: CreditCard,
  INVESTMENT: TrendingUp,
  CASH: DollarSign,
  OTHER: Building2,
};

const ACCOUNT_TYPE_COLORS: Record<AccountType, string> = {
  CHECKING: 'bg-blue-500',
  SAVINGS: 'bg-green-500',
  CREDIT_CARD: 'bg-red-500',
  INVESTMENT: 'bg-purple-500',
  CASH: 'bg-yellow-500',
  OTHER: 'bg-gray-500',
};

export function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [summary, setSummary] = useState<AccountSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [accountsData, summaryData] = await Promise.all([
        listAccounts(),
        getAccountSummary(),
      ]);
      setAccounts(accountsData);
      setSummary(summaryData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateAccount(data: {
    name: string;
    type: AccountType;
    balance?: number;
    institution?: string;
    account_number_last4?: string;
  }) {
    try {
      await createAccount(data);
      await loadData();
      setShowCreateModal(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create account');
    }
  }

  async function handleUpdateAccount(id: number, data: Partial<Account>) {
    try {
      await updateAccount(id, data);
      await loadData();
      setEditingAccount(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update account');
    }
  }

  async function handleDeleteAccount(id: number) {
    if (!confirm('Are you sure you want to delete this account? This action cannot be undone.')) {
      return;
    }
    try {
      await deleteAccount(id);
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete account');
    }
  }

  async function handleDeposit(id: number) {
    const amount = prompt('Enter deposit amount:');
    if (!amount) return;
    const description = prompt('Description (optional):');
    try {
      await depositToAccount(id, parseFloat(amount), description || undefined);
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to deposit funds');
    }
  }

  async function handleWithdraw(id: number) {
    const amount = prompt('Enter withdrawal amount:');
    if (!amount) return;
    const description = prompt('Description (optional):');
    try {
      await withdrawFromAccount(id, parseFloat(amount), description || undefined);
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to withdraw funds');
    }
  }

  async function handleTransfer() {
    const fromId = prompt('From Account ID:');
    const toId = prompt('To Account ID:');
    const amount = prompt('Transfer amount:');
    if (!fromId || !toId || !amount) return;
    const description = prompt('Description (optional):');
    try {
      await transferBetweenAccounts(
        parseInt(fromId),
        parseInt(toId),
        parseFloat(amount),
        description || undefined,
      );
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to transfer funds');
    }
  }

  function getAccountIcon(type: AccountType) {
    const Icon = ACCOUNT_TYPE_ICONS[type];
    return <Icon className="h-5 w-5" />;
  }

  function getAccountColor(type: AccountType) {
    return ACCOUNT_TYPE_COLORS[type];
  }

  const activeAccounts = accounts.filter((a) => a.active);
  const inactiveAccounts = accounts.filter((a) => !a.active);

  if (loading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading accounts...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold">Accounts</h1>
          <p className="text-muted-foreground mt-2">
            Manage all your financial accounts in one place
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleTransfer} variant="outline">
            <ArrowRightLeft className="mr-2 h-4 w-4" />
            Transfer
          </Button>
          <Button onClick={() => setShowCreateModal(true)} size="lg">
            <Plus className="mr-2 h-5 w-5" />
            New Account
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive text-destructive px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-6 md:grid-cols-3">
          <FinancialCard>
            <FinancialCardHeader>
              <FinancialCardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-green-500" />
                Total Assets
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-4xl font-bold text-green-600">
                ${summary.total_assets.toFixed(2)}
              </p>
              <p className="text-sm text-muted-foreground mt-1">{summary.currency}</p>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard>
            <FinancialCardHeader>
              <FinancialCardTitle className="flex items-center gap-2">
                <TrendingDown className="h-5 w-5 text-red-500" />
                Total Liabilities
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-4xl font-bold text-red-600">
                ${Math.abs(summary.total_liabilities).toFixed(2)}
              </p>
              <p className="text-sm text-muted-foreground mt-1">Credit cards & loans</p>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard>
            <FinancialCardHeader>
              <FinancialCardTitle className="flex items-center gap-2">
                <DollarSign className="h-5 w-5 text-blue-500" />
                Net Worth
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-4xl font-bold">
                ${summary.net_worth.toFixed(2)}
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                Assets - Liabilities
              </p>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Active Accounts */}
      <div className="space-y-4">
        <h2 className="text-2xl font-bold">Active Accounts</h2>
        {activeAccounts.length === 0 ? (
          <FinancialCard>
            <FinancialCardContent className="py-12 text-center">
              <Wallet className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-lg font-semibold mb-2">No accounts yet</p>
              <p className="text-muted-foreground mb-4">
                Add your first financial account to start tracking
              </p>
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Create Your First Account
              </Button>
            </FinancialCardContent>
          </FinancialCard>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {activeAccounts.map((account) => {
              const isLiability = account.balance < 0 || account.type === 'CREDIT_CARD';
              return (
                <FinancialCard
                  key={account.id}
                  className="hover:shadow-lg transition-shadow border-l-4"
                  style={{ borderLeftColor: account.color }}
                >
                  <FinancialCardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <FinancialCardTitle className="flex items-center gap-2">
                          <div className={`p-2 rounded-full ${getAccountColor(account.type)} text-white`}>
                            {getAccountIcon(account.type)}
                          </div>
                          {account.name}
                        </FinancialCardTitle>
                        <FinancialCardDescription>
                          {account.institution && (
                            <span className="flex items-center gap-1 mt-1">
                              <Building2 className="h-3 w-3" />
                              {account.institution}
                              {account.account_number_last4 && ` •••• ${account.account_number_last4}`}
                            </span>
                          )}
                        </FinancialCardDescription>
                      </div>
                      <Badge variant={isLiability ? 'destructive' : 'default'}>
                        {account.type.replace('_', ' ')}
                      </Badge>
                    </div>
                  </FinancialCardHeader>

                  <FinancialCardContent className="space-y-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Balance</p>
                      <p className={`text-3xl font-bold ${isLiability ? 'text-red-600' : 'text-green-600'}`}>
                        ${Math.abs(account.balance).toFixed(2)}
                      </p>
                      {isLiability && account.balance < 0 && (
                        <p className="text-xs text-muted-foreground mt-1">
                          (Owed)
                        </p>
                      )}
                    </div>
                  </FinancialCardContent>

                  <FinancialCardFooter className="flex gap-2 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleDeposit(account.id)}
                      className="flex-1"
                    >
                      <ArrowUpCircle className="h-4 w-4 mr-1" />
                      {isLiability ? 'Pay' : 'Deposit'}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleWithdraw(account.id)}
                      className="flex-1"
                    >
                      <ArrowDownCircle className="h-4 w-4 mr-1" />
                      {isLiability ? 'Charge' : 'Withdraw'}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setEditingAccount(account)}
                    >
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDeleteAccount(account.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </FinancialCardFooter>
                </FinancialCard>
              );
            })}
          </div>
        )}
      </div>

      {/* Inactive Accounts */}
      {inactiveAccounts.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-muted-foreground">Inactive Accounts</h2>
          <div className="grid gap-4 md:grid-cols-3 opacity-60">
            {inactiveAccounts.map((account) => (
              <FinancialCard key={account.id} className="border-dashed">
                <FinancialCardHeader>
                  <FinancialCardTitle className="flex items-center gap-2">
                    {getAccountIcon(account.type)}
                    {account.name}
                  </FinancialCardTitle>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <Badge variant="secondary">Inactive</Badge>
                </FinancialCardContent>
                <FinancialCardFooter>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleUpdateAccount(account.id, { active: true })}
                  >
                    Reactivate
                  </Button>
                </FinancialCardFooter>
              </FinancialCard>
            ))}
          </div>
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background p-6 rounded-lg shadow-xl max-w-md w-full">
            <h2 className="text-2xl font-bold mb-4">Add Account</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.currentTarget);
                handleCreateAccount({
                  name: formData.get('name') as string,
                  type: formData.get('type') as AccountType,
                  balance: parseFloat(formData.get('balance') as string) || 0,
                  institution: formData.get('institution') as string || undefined,
                  account_number_last4: formData.get('account_number_last4') as string || undefined,
                });
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm font-medium mb-1">Account Name *</label>
                <input
                  type="text"
                  name="name"
                  required
                  className="w-full border rounded px-3 py-2"
                  placeholder="My Checking Account"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Account Type *</label>
                <select name="type" required className="w-full border rounded px-3 py-2">
                  <option value="CHECKING">Checking</option>
                  <option value="SAVINGS">Savings</option>
                  <option value="CREDIT_CARD">Credit Card</option>
                  <option value="INVESTMENT">Investment</option>
                  <option value="CASH">Cash</option>
                  <option value="OTHER">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Current Balance</label>
                <input
                  type="number"
                  name="balance"
                  step="0.01"
                  className="w-full border rounded px-3 py-2"
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Institution</label>
                <input
                  type="text"
                  name="institution"
                  className="w-full border rounded px-3 py-2"
                  placeholder="Bank of America"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Last 4 Digits</label>
                <input
                  type="text"
                  name="account_number_last4"
                  maxLength={4}
                  pattern="[0-9]{4}"
                  className="w-full border rounded px-3 py-2"
                  placeholder="1234"
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button type="button" variant="outline" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </Button>
                <Button type="submit">Add Account</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
