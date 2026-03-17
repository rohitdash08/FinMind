import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import {
  getOverview,
  createAccount,
  updateAccount,
  deleteAccount,
  type AccountType,
  type AccountWithStats,
  type OverviewSummary,
} from '@/api/accounts';
import { Plus, Pencil, Trash2, Wallet, TrendingUp, TrendingDown, Hash } from 'lucide-react';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPES: AccountType[] = ['BANK', 'CREDIT', 'CASH', 'INVESTMENT', 'WALLET', 'OTHER'];

const TYPE_LABELS: Record<AccountType, string> = {
  BANK: 'Bank',
  CREDIT: 'Credit',
  CASH: 'Cash',
  INVESTMENT: 'Investment',
  WALLET: 'Wallet',
  OTHER: 'Other',
};

const TYPE_COLORS: Record<AccountType, string> = {
  BANK: 'bg-blue-100 text-blue-700',
  CREDIT: 'bg-red-100 text-red-700',
  CASH: 'bg-green-100 text-green-700',
  INVESTMENT: 'bg-purple-100 text-purple-700',
  WALLET: 'bg-yellow-100 text-yellow-700',
  OTHER: 'bg-gray-100 text-gray-700',
};

interface AccountFormState {
  name: string;
  account_type: AccountType;
  currency: string;
  initial_balance: string;
  color: string;
}

const DEFAULT_FORM: AccountFormState = {
  name: '',
  account_type: 'BANK',
  currency: 'INR',
  initial_balance: '0',
  color: '',
};

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

export function Accounts() {
  const { toast } = useToast();
  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const [accounts, setAccounts] = useState<AccountWithStats[]>([]);
  const [summary, setSummary] = useState<OverviewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<AccountWithStats | null>(null);
  const [form, setForm] = useState<AccountFormState>(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getOverview();
      setAccounts(data.accounts);
      setSummary(data.summary);
    } catch (err: unknown) {
      const msg = getErrorMessage(err, 'Failed to load accounts');
      setError(msg);
      toast({ title: 'Failed to load accounts', description: msg });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function openCreate() {
    setEditTarget(null);
    setForm(DEFAULT_FORM);
    setOpen(true);
  }

  function openEdit(account: AccountWithStats) {
    setEditTarget(account);
    setForm({
      name: account.name,
      account_type: account.account_type,
      currency: account.currency,
      initial_balance: String(account.initial_balance),
      color: account.color ?? '',
    });
    setOpen(true);
  }

  function setField<K extends keyof AccountFormState>(key: K, value: AccountFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSave() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        account_type: form.account_type,
        currency: form.currency.trim() || 'INR',
        initial_balance: parseFloat(form.initial_balance) || 0,
        color: form.color.trim() || undefined,
      };
      if (editTarget) {
        await updateAccount(editTarget.id, payload);
        toast({ title: 'Account updated' });
      } else {
        await createAccount(payload);
        toast({ title: 'Account created' });
      }
      setOpen(false);
      setForm(DEFAULT_FORM);
      setEditTarget(null);
      await refresh();
    } catch (err: unknown) {
      toast({ title: 'Failed to save account', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    setSaving(true);
    try {
      await deleteAccount(id);
      toast({ title: 'Account deleted' });
      await refresh();
    } catch (err: unknown) {
      toast({ title: 'Failed to delete account', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  const netWorthPositive = (summary?.net_worth ?? 0) >= 0;

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex items-center justify-between gap-3">
          <div>
            <h1 className="page-title">Accounts</h1>
            <p className="page-subtitle">Manage your financial accounts and see the big picture.</p>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button onClick={openCreate}>
                <Plus className="w-4 h-4" />
                New Account
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{editTarget ? 'Edit Account' : 'New Account'}</DialogTitle>
                <DialogDescription>
                  {editTarget ? 'Update your account details.' : 'Add a new financial account.'}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label htmlFor="acc-name">Name *</Label>
                  <Input
                    id="acc-name"
                    value={form.name}
                    onChange={(e) => setField('name', e.target.value)}
                    placeholder="e.g. HDFC Savings"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="acc-type">Account Type</Label>
                    <select
                      id="acc-type"
                      className="input"
                      value={form.account_type}
                      onChange={(e) => setField('account_type', e.target.value as AccountType)}
                    >
                      {ACCOUNT_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {TYPE_LABELS[t]}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <Label htmlFor="acc-currency">Currency</Label>
                    <Input
                      id="acc-currency"
                      value={form.currency}
                      onChange={(e) => setField('currency', e.target.value)}
                      placeholder="INR"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="acc-balance">Initial Balance</Label>
                    <Input
                      id="acc-balance"
                      type="number"
                      value={form.initial_balance}
                      onChange={(e) => setField('initial_balance', e.target.value)}
                      placeholder="0"
                    />
                  </div>
                  <div>
                    <Label htmlFor="acc-color">Color (optional)</Label>
                    <div className="flex gap-2">
                      <input
                        id="acc-color-picker"
                        type="color"
                        className="h-9 w-12 cursor-pointer rounded border border-input p-1"
                        value={form.color || '#6366f1'}
                        onChange={(e) => setField('color', e.target.value)}
                      />
                      <Input
                        id="acc-color"
                        value={form.color}
                        onChange={(e) => setField('color', e.target.value)}
                        placeholder="#6366f1"
                      />
                    </div>
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>
                  Cancel
                </Button>
                <Button onClick={onSave} disabled={saving || !form.name.trim()}>
                  {editTarget ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {error && <div className="error mb-4">{error}</div>}

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <FinancialCard variant="financial" className="group card-interactive fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Assets
              </FinancialCardTitle>
              <TrendingUp className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : currency(summary?.total_assets ?? 0)}
            </div>
            <div className="text-sm text-muted-foreground">All positive balances</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="group card-interactive fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Liabilities
              </FinancialCardTitle>
              <TrendingDown className="w-5 h-5 text-muted-foreground group-hover:text-destructive transition-colors" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : currency(summary?.total_liabilities ?? 0)}
            </div>
            <div className="text-sm text-muted-foreground">All negative balances</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="group card-interactive fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Net Worth
              </FinancialCardTitle>
              <Wallet className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div
              className={`metric-value mb-1 ${
                loading ? 'text-foreground' : netWorthPositive ? 'text-success' : 'text-destructive'
              }`}
            >
              {loading ? '...' : currency(summary?.net_worth ?? 0)}
            </div>
            <div className="text-sm text-muted-foreground">Assets minus liabilities</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="group card-interactive fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Account Count
              </FinancialCardTitle>
              <Hash className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : (summary?.account_count ?? 0)}
            </div>
            <div className="text-sm text-muted-foreground">Active accounts</div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Accounts List */}
      <FinancialCard variant="financial" className="fade-in-up">
        <FinancialCardHeader>
          <FinancialCardTitle className="section-title">Your Accounts</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />
              ))}
            </div>
          ) : accounts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Wallet className="w-12 h-12 text-muted-foreground mb-3" />
              <p className="text-sm text-muted-foreground">
                No accounts yet — add your first account
              </p>
              <Button className="mt-4" onClick={openCreate}>
                <Plus className="w-4 h-4" />
                Add Account
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              {accounts.map((account) => (
                <div
                  key={account.id}
                  className="interactive-row flex items-center justify-between border-b py-3 last:border-b-0"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {account.color && (
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: account.color }}
                      />
                    )}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-foreground">{account.name}</span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[account.account_type]}`}
                        >
                          {TYPE_LABELS[account.account_type]}
                        </span>
                        <span className="text-xs text-muted-foreground">{account.currency}</span>
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        Income: {currency(account.income, account.currency)} · Expenses:{' '}
                        {currency(account.expenses, account.currency)}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 flex-shrink-0">
                    <span
                      className={`font-semibold ${
                        account.balance >= 0 ? 'text-success' : 'text-destructive'
                      }`}
                    >
                      {currency(account.balance, account.currency)}
                    </span>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(account)}
                        aria-label="Edit account"
                      >
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon" aria-label="Delete account">
                            <Trash2 className="w-4 h-4 text-destructive" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete account?</AlertDialogTitle>
                            <AlertDialogDescription>
                              "{account.name}" will be deactivated. This cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => onDelete(account.id)}>
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}

export default Accounts;
