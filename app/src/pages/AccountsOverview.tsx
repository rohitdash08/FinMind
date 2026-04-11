import { useEffect, useState, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  CreditCard,
  Plus,
  Pencil,
  Trash2,
  Landmark,
  PiggyBank,
  Banknote,
  BarChart3,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  getAccountsOverview,
  createAccount,
  updateAccount,
  deleteAccount,
  type FinancialAccount,
  type AccountsOverview as AccountsOverviewData,
  type AccountType,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';
import { useToast } from '@/hooks/use-toast';

const ACCOUNT_TYPE_OPTIONS: { value: AccountType; label: string }[] = [
  { value: 'CHECKING', label: 'Checking' },
  { value: 'SAVINGS', label: 'Savings' },
  { value: 'CREDIT', label: 'Credit Card' },
  { value: 'INVESTMENT', label: 'Investment' },
  { value: 'CASH', label: 'Cash' },
];

const ACCOUNT_TYPE_ICONS: Record<AccountType, typeof Wallet> = {
  CHECKING: Landmark,
  SAVINGS: PiggyBank,
  CREDIT: CreditCard,
  INVESTMENT: BarChart3,
  CASH: Banknote,
};

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

type AccountFormData = {
  name: string;
  account_type: AccountType;
  balance: string;
  currency: string;
};

const EMPTY_FORM: AccountFormData = {
  name: '',
  account_type: 'CHECKING',
  balance: '0',
  currency: 'USD',
};

export function AccountsOverview() {
  const { toast } = useToast();
  const [data, setData] = useState<AccountsOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<FinancialAccount | null>(null);
  const [form, setForm] = useState<AccountFormData>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAccountsOverview();
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  function openCreateDialog() {
    setEditingAccount(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEditDialog(account: FinancialAccount) {
    setEditingAccount(account);
    setForm({
      name: account.name,
      account_type: account.account_type,
      balance: String(account.balance),
      currency: account.currency,
    });
    setDialogOpen(true);
  }

  async function handleSubmit() {
    if (!form.name.trim()) {
      toast({ title: 'Validation Error', description: 'Account name is required.', variant: 'destructive' });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        account_type: form.account_type,
        balance: parseFloat(form.balance) || 0,
        currency: form.currency || 'USD',
      };
      if (editingAccount) {
        await updateAccount(editingAccount.id, payload);
        toast({ title: 'Account Updated', description: `${payload.name} has been updated.` });
      } else {
        await createAccount(payload);
        toast({ title: 'Account Created', description: `${payload.name} has been added.` });
      }
      setDialogOpen(false);
      await loadData();
    } catch (err: unknown) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Something went wrong.',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(account: FinancialAccount) {
    try {
      await deleteAccount(account.id);
      toast({ title: 'Account Deleted', description: `${account.name} has been removed.` });
      await loadData();
    } catch (err: unknown) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to delete account.',
        variant: 'destructive',
      });
    }
  }

  const summary = data?.summary;
  const accounts = data?.accounts ?? [];

  const summaryCards = [
    {
      title: 'Net Worth',
      amount: currency(summary?.net_worth ?? 0),
      trend: (summary?.net_worth ?? 0) >= 0 ? 'up' : 'down',
      icon: Wallet,
      description: 'Assets minus liabilities',
    },
    {
      title: 'Total Assets',
      amount: currency(summary?.total_assets ?? 0),
      trend: 'up' as const,
      icon: TrendingUp,
      description: 'Checking, savings, investments, cash',
    },
    {
      title: 'Total Liabilities',
      amount: currency(summary?.total_liabilities ?? 0),
      trend: 'down' as const,
      icon: TrendingDown,
      description: 'Credit card balances',
    },
    {
      title: 'Accounts',
      amount: String(summary?.total_accounts ?? 0),
      trend: 'up' as const,
      icon: CreditCard,
      description: 'Active financial accounts',
    },
  ] as const;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Accounts Overview</h1>
            <p className="page-subtitle">Multi-account financial snapshot across all your accounts.</p>
          </div>
          <div className="flex gap-3">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="financial" size="sm" onClick={openCreateDialog}>
                  <Plus className="w-4 h-4" />
                  Add Account
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{editingAccount ? 'Edit Account' : 'Add Account'}</DialogTitle>
                  <DialogDescription>
                    {editingAccount
                      ? 'Update your account details below.'
                      : 'Add a new financial account to track.'}
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div>
                    <label htmlFor="account-name" className="text-sm font-medium text-foreground">
                      Account Name
                    </label>
                    <input
                      id="account-name"
                      type="text"
                      className="input mt-1 w-full"
                      placeholder="e.g. Main Checking"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label htmlFor="account-type" className="text-sm font-medium text-foreground">
                      Account Type
                    </label>
                    <select
                      id="account-type"
                      className="input mt-1 w-full"
                      value={form.account_type}
                      onChange={(e) => setForm({ ...form, account_type: e.target.value as AccountType })}
                    >
                      {ACCOUNT_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="account-balance" className="text-sm font-medium text-foreground">
                      Balance
                    </label>
                    <input
                      id="account-balance"
                      type="number"
                      step="0.01"
                      className="input mt-1 w-full"
                      placeholder="0.00"
                      value={form.balance}
                      onChange={(e) => setForm({ ...form, balance: e.target.value })}
                    />
                  </div>
                  <div>
                    <label htmlFor="account-currency" className="text-sm font-medium text-foreground">
                      Currency
                    </label>
                    <input
                      id="account-currency"
                      type="text"
                      className="input mt-1 w-full"
                      placeholder="USD"
                      value={form.currency}
                      onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setDialogOpen(false)}>
                    Cancel
                  </Button>
                  <Button variant="financial" onClick={() => void handleSubmit()} disabled={submitting}>
                    {submitting ? 'Saving...' : editingAccount ? 'Update' : 'Create'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}. Showing empty fallback state.</div>}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
        {summaryCards.map((card, index) => (
          <FinancialCard key={index} variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  {card.title}
                </FinancialCardTitle>
                <card.icon className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">{loading ? '...' : card.amount}</div>
              <div className="text-sm text-muted-foreground">{card.description}</div>
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      <FinancialCard variant="financial" className="fade-in-up">
        <FinancialCardHeader>
          <div className="flex items-center justify-between">
            <FinancialCardTitle className="section-title">All Accounts</FinancialCardTitle>
            <span className="text-sm text-muted-foreground">{accounts.length} account(s)</span>
          </div>
          <FinancialCardDescription>Manage and view balances across all your financial accounts</FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          {accounts.length === 0 ? (
            <div className="text-center py-12">
              <Wallet className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground mb-4">No accounts yet. Add your first financial account to get started.</p>
              <Button variant="financial" size="sm" onClick={openCreateDialog}>
                <Plus className="w-4 h-4" />
                Add Your First Account
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {accounts.map((account) => {
                const Icon = ACCOUNT_TYPE_ICONS[account.account_type] || Wallet;
                const isCredit = account.account_type === 'CREDIT';
                const balanceColor = isCredit
                  ? 'text-destructive'
                  : account.balance > 0
                    ? 'text-success'
                    : 'text-foreground';

                return (
                  <div key={account.id} className="interactive-row flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div
                        className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                          isCredit ? 'bg-destructive-light text-destructive' : 'bg-success-light text-success'
                        }`}
                      >
                        <Icon className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="font-medium text-foreground">{account.name}</div>
                        <div className="text-sm text-muted-foreground">
                          {ACCOUNT_TYPE_OPTIONS.find((o) => o.value === account.account_type)?.label ??
                            account.account_type}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className={`font-semibold ${balanceColor}`}>
                        {currency(account.balance, account.currency)}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEditDialog(account)}
                        aria-label={`Edit ${account.name}`}
                      >
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void handleDelete(account)}
                        aria-label={`Delete ${account.name}`}
                      >
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>

      {summary && Object.keys(summary.by_type).length > 0 && (
        <FinancialCard variant="financial" className="fade-in-up mt-8">
          <FinancialCardHeader>
            <FinancialCardTitle className="section-title">Balance by Account Type</FinancialCardTitle>
            <FinancialCardDescription>Distribution of funds across account types</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-3">
              {Object.entries(summary.by_type).map(([type, balance]) => {
                const total = summary.total_assets + summary.total_liabilities;
                const pct = total > 0 ? (Math.abs(balance) / total) * 100 : 0;
                const label =
                  ACCOUNT_TYPE_OPTIONS.find((o) => o.value === type)?.label ?? type;
                return (
                  <div key={type} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-foreground">{label}</span>
                      <span className="text-muted-foreground">
                        {currency(balance)} ({pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="chart-track h-2">
                      <div
                        className="chart-fill-primary h-2"
                        style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}
    </div>
  );
}
