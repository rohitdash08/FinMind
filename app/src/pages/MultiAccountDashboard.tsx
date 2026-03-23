import { useEffect, useState, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { formatMoney } from '@/lib/currency';
import {
  type FinancialAccount,
  type AccountType,
  type MultiAccountOverview,
  type CreateAccountPayload,
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  getMultiAccountOverview,
} from '@/api/accounts';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  CreditCard,
  PiggyBank,
  Banknote,
  BarChart3,
  Plus,
  Pencil,
  Trash2,
  RefreshCw,
  Building2,
  Eye,
  EyeOff,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ACCOUNT_TYPE_OPTIONS: { value: AccountType; label: string }[] = [
  { value: 'CHECKING', label: 'Checking' },
  { value: 'SAVINGS', label: 'Savings' },
  { value: 'CREDIT_CARD', label: 'Credit Card' },
  { value: 'INVESTMENT', label: 'Investment' },
  { value: 'LOAN', label: 'Loan' },
  { value: 'CASH', label: 'Cash' },
  { value: 'OTHER', label: 'Other' },
];

const SUPPORTED_CURRENCIES = [
  'INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD', 'JPY',
];

function accountTypeIcon(type: AccountType) {
  switch (type) {
    case 'CHECKING': return <Banknote className="h-4 w-4" />;
    case 'SAVINGS': return <PiggyBank className="h-4 w-4" />;
    case 'CREDIT_CARD': return <CreditCard className="h-4 w-4" />;
    case 'INVESTMENT': return <BarChart3 className="h-4 w-4" />;
    case 'LOAN': return <TrendingDown className="h-4 w-4" />;
    case 'CASH': return <Wallet className="h-4 w-4" />;
    default: return <Building2 className="h-4 w-4" />;
  }
}

const LIABILITY_TYPES: AccountType[] = ['CREDIT_CARD', 'LOAN'];

function isLiability(type: AccountType) {
  return LIABILITY_TYPES.includes(type);
}

// ---------------------------------------------------------------------------
// Account Form (create / edit)
// ---------------------------------------------------------------------------

type AccountFormState = {
  name: string;
  account_type: AccountType;
  balance: string;
  currency: string;
  institution: string;
  last_four: string;
  color: string;
  include_in_overview: boolean;
};

const DEFAULT_FORM: AccountFormState = {
  name: '',
  account_type: 'CHECKING',
  balance: '0',
  currency: 'INR',
  institution: '',
  last_four: '',
  color: '#4f46e5',
  include_in_overview: true,
};

function AccountFormDialog({
  open,
  onClose,
  initial,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  initial?: AccountFormState;
  onSave: (data: AccountFormState) => Promise<void>;
}) {
  const [form, setForm] = useState<AccountFormState>(initial ?? DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  // Sync form when initial changes (editing different account)
  useEffect(() => {
    setForm(initial ?? DEFAULT_FORM);
  }, [initial, open]);

  const set = (key: keyof AccountFormState, value: string | boolean) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(form);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{initial ? 'Edit Account' : 'Add Account'}</DialogTitle>
          <DialogDescription>
            {initial ? 'Update your financial account details.' : 'Add a new financial account to track.'}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          {/* Name */}
          <div className="space-y-1">
            <Label htmlFor="acc-name">Account Name *</Label>
            <Input
              id="acc-name"
              placeholder="e.g. HDFC Savings"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
            />
          </div>

          {/* Type */}
          <div className="space-y-1">
            <Label htmlFor="acc-type">Account Type</Label>
            <Select
              value={form.account_type}
              onValueChange={(v) => set('account_type', v)}
            >
              <SelectTrigger id="acc-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACCOUNT_TYPE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Balance + Currency row */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="acc-balance">Balance</Label>
              <Input
                id="acc-balance"
                type="number"
                step="0.01"
                value={form.balance}
                onChange={(e) => set('balance', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="acc-currency">Currency</Label>
              <Select
                value={form.currency}
                onValueChange={(v) => set('currency', v)}
              >
                <SelectTrigger id="acc-currency">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SUPPORTED_CURRENCIES.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Institution */}
          <div className="space-y-1">
            <Label htmlFor="acc-institution">Institution (optional)</Label>
            <Input
              id="acc-institution"
              placeholder="e.g. HDFC Bank"
              value={form.institution}
              onChange={(e) => set('institution', e.target.value)}
            />
          </div>

          {/* Last four */}
          <div className="space-y-1">
            <Label htmlFor="acc-last4">Last 4 digits (optional)</Label>
            <Input
              id="acc-last4"
              placeholder="1234"
              maxLength={4}
              value={form.last_four}
              onChange={(e) => set('last_four', e.target.value.replace(/\D/g, ''))}
            />
          </div>

          {/* Color + Include in overview row */}
          <div className="grid grid-cols-2 gap-3 items-center">
            <div className="space-y-1">
              <Label htmlFor="acc-color">Color tag</Label>
              <div className="flex items-center gap-2">
                <input
                  id="acc-color"
                  type="color"
                  value={form.color}
                  onChange={(e) => set('color', e.target.value)}
                  className="h-9 w-9 rounded cursor-pointer border border-input"
                />
                <span className="text-xs text-muted-foreground">{form.color}</span>
              </div>
            </div>
            <div className="space-y-1">
              <Label>Include in overview</Label>
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => set('include_in_overview', !form.include_in_overview)}
                  className={`flex items-center gap-1 text-sm font-medium rounded px-3 py-1.5 border transition ${
                    form.include_in_overview
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-muted text-muted-foreground border-border'
                  }`}
                >
                  {form.include_in_overview ? (
                    <><Eye className="h-3.5 w-3.5" /> Yes</>
                  ) : (
                    <><EyeOff className="h-3.5 w-3.5" /> No</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || !form.name.trim()}>
            {saving ? 'Saving…' : initial ? 'Update' : 'Add Account'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Account card
// ---------------------------------------------------------------------------

function AccountCard({
  account,
  onEdit,
  onDelete,
}: {
  account: FinancialAccount;
  onEdit: (a: FinancialAccount) => void;
  onDelete: (a: FinancialAccount) => void;
}) {
  const liability = isLiability(account.account_type);
  const colorStyle = account.color ? { borderLeftColor: account.color } : {};

  return (
    <div
      className="relative rounded-xl border-l-4 bg-card p-4 shadow-sm hover:shadow-md transition-shadow"
      style={colorStyle}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-primary-foreground"
            style={{ backgroundColor: account.color ?? '#4f46e5' }}
          >
            {accountTypeIcon(account.account_type)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{account.name}</p>
            {account.institution && (
              <p className="truncate text-xs text-muted-foreground">{account.institution}</p>
            )}
            {account.last_four && (
              <p className="text-xs text-muted-foreground">••••&nbsp;{account.last_four}</p>
            )}
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            onClick={() => onEdit(account)}
            aria-label="Edit account"
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-destructive hover:text-destructive"
            onClick={() => onDelete(account)}
            aria-label="Delete account"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="mt-3 flex items-end justify-between">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">
            {ACCOUNT_TYPE_OPTIONS.find((o) => o.value === account.account_type)?.label ?? account.account_type}
          </p>
          <p
            className={`text-lg font-bold tabular-nums ${
              liability ? 'text-destructive' : 'text-foreground'
            }`}
          >
            {liability ? '-' : ''}
            {formatMoney(Math.abs(account.balance), account.currency)}
          </p>
        </div>
        {!account.include_in_overview && (
          <span className="flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            <EyeOff className="h-2.5 w-2.5" /> Hidden
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function MultiAccountDashboard() {
  const { toast } = useToast();
  const [overview, setOverview] = useState<MultiAccountOverview | null>(null);
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<FinancialAccount | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, accs] = await Promise.all([
        getMultiAccountOverview(month),
        listAccounts(),
      ]);
      setOverview(ov);
      setAccounts(accs);
    } catch (err) {
      toast({
        title: 'Failed to load accounts',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [month, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async (form: AccountFormState) => {
    const payload: CreateAccountPayload = {
      name: form.name.trim(),
      account_type: form.account_type,
      balance: parseFloat(form.balance) || 0,
      currency: form.currency,
      institution: form.institution.trim() || undefined,
      last_four: form.last_four.trim() || undefined,
      color: form.color || undefined,
      include_in_overview: form.include_in_overview,
    };

    try {
      if (editTarget) {
        await updateAccount(editTarget.id, payload);
        toast({ title: 'Account updated' });
      } else {
        await createAccount(payload);
        toast({ title: 'Account added' });
      }
      await load();
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to save account',
        variant: 'destructive',
      });
      throw err; // re-throw so dialog stays open on error
    }
  };

  const handleEdit = (account: FinancialAccount) => {
    setEditTarget(account);
    setDialogOpen(true);
  };

  const handleDelete = async (account: FinancialAccount) => {
    if (!window.confirm(`Deactivate "${account.name}"? It will be hidden from your dashboard.`)) return;
    try {
      await deleteAccount(account.id);
      toast({ title: 'Account deactivated', description: account.name });
      await load();
    } catch (err) {
      toast({
        title: 'Failed to deactivate',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const editFormInitial: AccountFormState | undefined = editTarget
    ? {
        name: editTarget.name,
        account_type: editTarget.account_type,
        balance: String(editTarget.balance),
        currency: editTarget.currency,
        institution: editTarget.institution ?? '',
        last_four: editTarget.last_four ?? '',
        color: editTarget.color ?? '#4f46e5',
        include_in_overview: editTarget.include_in_overview,
      }
    : undefined;

  const totals = overview?.totals;
  const ms = overview?.monthly_summary;

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Multi-Account Overview</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            All your financial accounts in one place
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setEditTarget(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Add Account
          </Button>
        </div>
      </div>

      {/* Net Worth Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-1.5">
              <Wallet className="h-4 w-4 text-primary" />
              Net Worth
            </FinancialCardTitle>
            <FinancialCardDescription>Assets minus liabilities</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className={`text-2xl font-bold tabular-nums ${(totals?.net_worth ?? 0) >= 0 ? 'text-green-600' : 'text-destructive'}`}>
              {loading ? '—' : formatMoney(totals?.net_worth ?? 0)}
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-green-500" />
              Total Assets
            </FinancialCardTitle>
            <FinancialCardDescription>Checking, savings, investments</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-2xl font-bold tabular-nums text-green-600">
              {loading ? '—' : formatMoney(totals?.total_assets ?? 0)}
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-1.5">
              <TrendingDown className="h-4 w-4 text-destructive" />
              Total Liabilities
            </FinancialCardTitle>
            <FinancialCardDescription>Credit cards, loans</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-2xl font-bold tabular-nums text-destructive">
              {loading ? '—' : formatMoney(totals?.total_liabilities ?? 0)}
            </p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Monthly Summary */}
      <div className="grid gap-4 sm:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>Monthly Income</FinancialCardTitle>
            <FinancialCardDescription>{month}</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xl font-semibold tabular-nums text-green-600">
              {loading ? '—' : formatMoney(ms?.income ?? 0)}
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>Monthly Expenses</FinancialCardTitle>
            <FinancialCardDescription>{month}</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xl font-semibold tabular-nums text-destructive">
              {loading ? '—' : formatMoney(ms?.expenses ?? 0)}
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>Net Cash Flow</FinancialCardTitle>
            <FinancialCardDescription>{month}</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className={`text-xl font-semibold tabular-nums ${(ms?.net_flow ?? 0) >= 0 ? 'text-green-600' : 'text-destructive'}`}>
              {loading ? '—' : formatMoney(ms?.net_flow ?? 0)}
            </p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Accounts Grid */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Your Accounts</h2>
        {loading ? (
          <p className="text-muted-foreground text-sm">Loading…</p>
        ) : accounts.length === 0 ? (
          <div className="rounded-xl border border-dashed p-8 text-center">
            <Wallet className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
            <p className="text-muted-foreground">No accounts yet.</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => {
                setEditTarget(null);
                setDialogOpen(true);
              }}
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add your first account
            </Button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {accounts.map((acct) => (
              <AccountCard
                key={acct.id}
                account={acct}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      {/* Upcoming Bills (from overview) */}
      {(overview?.upcoming_bills?.length ?? 0) > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Upcoming Bills</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {overview!.upcoming_bills.map((b) => (
              <div
                key={b.id}
                className="flex items-center justify-between rounded-lg border bg-card px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium">{b.name}</p>
                  <p className="text-xs text-muted-foreground">
                    Due {new Date(b.next_due_date).toLocaleDateString()} · {b.cadence}
                  </p>
                </div>
                <p className="text-sm font-semibold tabular-nums">
                  {formatMoney(b.amount, b.currency)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Category Breakdown */}
      {(overview?.category_breakdown?.length ?? 0) > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Expense Breakdown — {month}</h2>
          <FinancialCard>
            <FinancialCardContent className="pt-4">
              <div className="space-y-2">
                {overview!.category_breakdown.map((c) => (
                  <div key={c.category_id ?? 'uncategorized'} className="flex items-center gap-3">
                    <div className="w-28 shrink-0 text-xs text-muted-foreground truncate">
                      {c.category_name}
                    </div>
                    <div className="flex-1">
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${c.share_pct}%` }}
                        />
                      </div>
                    </div>
                    <div className="w-16 shrink-0 text-right text-xs font-medium tabular-nums">
                      {formatMoney(c.amount)}
                    </div>
                    <div className="w-10 shrink-0 text-right text-xs text-muted-foreground">
                      {c.share_pct.toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Account form dialog */}
      <AccountFormDialog
        open={dialogOpen}
        onClose={() => {
          setDialogOpen(false);
          setEditTarget(null);
        }}
        initial={editFormInitial}
        onSave={handleSave}
      />
    </div>
  );
}

export default MultiAccountDashboard;
