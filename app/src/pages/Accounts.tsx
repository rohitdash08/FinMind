import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  Wallet,
  Plus,
  Landmark,
  PiggyBank,
  CreditCard,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import { getAccounts, createAccount, getAccountsOverview, type Account, type AccountType, type AccountsOverview } from '@/api/accounts';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

const ACCOUNT_TYPE_META: Record<AccountType, { label: string; icon: typeof Wallet; color: string }> = {
  CURRENT: { label: 'Current', icon: Landmark, color: 'bg-primary/10 text-primary' },
  SAVINGS: { label: 'Savings', icon: PiggyBank, color: 'bg-success/10 text-success' },
  CREDIT: { label: 'Credit Card', icon: CreditCard, color: 'bg-destructive/10 text-destructive' },
  INVESTMENT: { label: 'Investment', icon: TrendingUp, color: 'bg-warning/10 text-warning' },
};

const ALLOCATION_COLORS: Record<AccountType, string> = {
  CURRENT: 'bg-primary',
  SAVINGS: 'bg-success',
  CREDIT: 'bg-destructive',
  INVESTMENT: 'bg-warning',
};

export function Accounts() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [overview, setOverview] = useState<AccountsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add account dialog state
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<AccountType>('CURRENT');
  const [newBalance, setNewBalance] = useState('');
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [acc, ov] = await Promise.all([getAccounts(), getAccountsOverview()]);
      setAccounts(acc);
      setOverview(ov);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load accounts';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate() {
    if (!newName.trim()) return;
    setSaving(true);
    try {
      await createAccount({
        name: newName.trim(),
        type: newType,
        balance: newBalance ? Number(newBalance) : 0,
      });
      await refresh();
      setOpen(false);
      setNewName('');
      setNewType('CURRENT');
      setNewBalance('');
      toast({ title: 'Account created' });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create account';
      toast({ title: 'Failed to create account', description: msg });
    } finally {
      setSaving(false);
    }
  }

  const totalBalance = overview?.total_balance ?? accounts.reduce((s, a) => s + Number(a.balance || 0), 0);
  const currencyCode = overview?.currency ?? 'USD';

  const summaryCards = useMemo(() => {
    const isPositive = totalBalance >= 0;
    return [
      {
        title: 'Total Balance',
        amount: currency(totalBalance, currencyCode),
        change: isPositive ? 'Positive' : 'Negative',
        trend: isPositive ? 'up' : 'down' as const,
        icon: Wallet,
        description: `${overview?.accounts_count ?? accounts.length} account(s)`,
      },
    ];
  }, [totalBalance, currencyCode, overview, accounts.length]);

  const allocation = overview?.allocation ?? [];

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Accounts</h1>
            <p className="page-subtitle">Multi-account financial overview</p>
          </div>
          <div className="flex gap-3">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button variant="financial" size="sm">
                  <Plus className="w-4 h-4" />
                  Add Account
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>New Account</DialogTitle>
                  <DialogDescription>Add a new financial account to track.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm mb-1">Name</label>
                    <input
                      className="input w-full"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="e.g. Main Checking"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm mb-1">Type</label>
                      <select
                        className="input w-full"
                        value={newType}
                        onChange={(e) => setNewType(e.target.value as AccountType)}
                      >
                        <option value="CURRENT">Current</option>
                        <option value="SAVINGS">Savings</option>
                        <option value="CREDIT">Credit Card</option>
                        <option value="INVESTMENT">Investment</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm mb-1">Initial Balance</label>
                      <input
                        className="input w-full"
                        type="number"
                        min="0"
                        step="0.01"
                        value={newBalance}
                        onChange={(e) => setNewBalance(e.target.value)}
                        placeholder="0.00"
                      />
                    </div>
                  </div>
                </div>
                {error && <div className="error mt-2">{error}</div>}
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>
                    Cancel
                  </Button>
                  <Button onClick={onCreate} disabled={saving || !newName.trim()}>
                    Create
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      {/* Summary cards */}
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
              <div className="flex items-center text-sm">
                {card.trend === 'up' ? (
                  <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                ) : (
                  <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                )}
                <span
                  className={
                    card.trend === 'up'
                      ? 'text-success font-medium mr-2'
                      : 'text-destructive font-medium mr-2'
                  }
                >
                  {card.change}
                </span>
                <span className="text-muted-foreground">{card.description}</span>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Account list */}
        <div className="lg:col-span-2">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="section-title">Your Accounts</FinancialCardTitle>
              </div>
              <FinancialCardDescription>All linked financial accounts</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {loading ? (
                <div className="text-sm text-muted-foreground">Loading...</div>
              ) : accounts.length === 0 ? (
                <div className="text-sm text-muted-foreground">
                  No accounts yet. Add your first account to get started.
                </div>
              ) : (
                <div className="space-y-3">
                  {accounts.map((account) => {
                    const meta = ACCOUNT_TYPE_META[account.type] || ACCOUNT_TYPE_META.CURRENT;
                    const Icon = meta.icon;
                    const isCredit = account.type === 'CREDIT';
                    return (
                      <div key={account.id} className="interactive-row flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <div
                            className={`w-10 h-10 rounded-lg flex items-center justify-center ${meta.color}`}
                          >
                            <Icon className="w-5 h-5" />
                          </div>
                          <div>
                            <div className="font-medium text-foreground">
                              {account.name}
                              {account.is_default && (
                                <span className="ml-2 text-xs text-muted-foreground font-normal">
                                  (default)
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-muted-foreground">{meta.label}</div>
                          </div>
                        </div>
                        <div
                          className={`font-semibold ${
                            isCredit && Number(account.balance) > 0
                              ? 'text-destructive'
                              : 'text-foreground'
                          }`}
                        >
                          {currency(account.balance, account.currency)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </FinancialCardContent>
            <FinancialCardFooter>
              <Button
                variant="financial"
                size="sm"
                className="w-full"
                onClick={() => setOpen(true)}
              >
                <Plus className="w-4 h-4" />
                Add New Account
              </Button>
            </FinancialCardFooter>
          </FinancialCard>
        </div>

        {/* Sidebar: Asset allocation */}
        <div className="space-y-6">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Asset Allocation</FinancialCardTitle>
              <FinancialCardDescription>Balance distribution by account type</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {allocation.length === 0 ? (
                <div className="text-sm text-muted-foreground">No allocation data available.</div>
              ) : (
                <div className="space-y-3">
                  {allocation.map((row) => {
                    const meta = ACCOUNT_TYPE_META[row.type] || ACCOUNT_TYPE_META.CURRENT;
                    const barColor = ALLOCATION_COLORS[row.type] || 'bg-primary';
                    return (
                      <div key={row.type} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-foreground">{meta.label}</span>
                          <span className="text-muted-foreground">
                            {currency(row.balance, currencyCode)} ({row.share_pct.toFixed(0)}%)
                          </span>
                        </div>
                        <div className="chart-track h-2">
                          <div
                            className={`${barColor} h-2 rounded-full transition-all`}
                            style={{
                              width: `${Math.max(2, Math.min(100, row.share_pct))}%`,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Quick type summary */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Account Types</FinancialCardTitle>
              <FinancialCardDescription>Number of accounts by type</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {accounts.length === 0 ? (
                <div className="text-sm text-muted-foreground">No accounts yet.</div>
              ) : (
                <div className="space-y-2">
                  {(Object.entries(ACCOUNT_TYPE_META) as [AccountType, typeof ACCOUNT_TYPE_META[AccountType]][]).map(
                    ([type, meta]) => {
                      const count = accounts.filter((a) => a.type === type).length;
                      if (count === 0) return null;
                      const Icon = meta.icon;
                      return (
                        <div key={type} className="interactive-row flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <div
                              className={`w-8 h-8 rounded-lg flex items-center justify-center ${meta.color}`}
                            >
                              <Icon className="w-4 h-4" />
                            </div>
                            <span className="text-sm font-medium text-foreground">{meta.label}</span>
                          </div>
                          <span className="text-sm text-muted-foreground">{count}</span>
                        </div>
                      );
                    },
                  )}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      </div>
    </div>
  );
}
