import { useState, useEffect, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import {
  Wallet, PlusCircle, Pencil, Trash2, TrendingUp, TrendingDown, Landmark, CreditCard,
  Banknote, PiggyBank, X, Check,
} from 'lucide-react';
import {
  listAccounts, getAccountsOverview, createAccount, updateAccount, deleteAccount,
  type FinancialAccount, type AccountsOverview, type AccountType,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPES: AccountType[] = ['BANK', 'CREDIT', 'CASH', 'INVESTMENT', 'WALLET', 'OTHER'];

const TYPE_ICON: Record<AccountType, React.ReactNode> = {
  BANK: <Landmark className="w-4 h-4" />,
  CREDIT: <CreditCard className="w-4 h-4" />,
  CASH: <Banknote className="w-4 h-4" />,
  INVESTMENT: <TrendingUp className="w-4 h-4" />,
  WALLET: <PiggyBank className="w-4 h-4" />,
  OTHER: <Wallet className="w-4 h-4" />,
};

const ACCENT_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6', '#ec4899'];

function AccountCard({
  account,
  onEdit,
  onDelete,
}: {
  account: FinancialAccount & { total_income?: number; total_spent?: number };
  onEdit: (a: FinancialAccount) => void;
  onDelete: (id: number) => void;
}) {
  const isPositive = account.current_balance >= 0;
  const accent = account.color || '#6366f1';

  return (
    <FinancialCard className="relative overflow-hidden">
      <div
        className="absolute top-0 left-0 w-1 h-full rounded-l-xl"
        style={{ backgroundColor: accent }}
      />
      <FinancialCardContent className="pt-4 pl-5">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <span style={{ color: accent }}>{TYPE_ICON[account.account_type as AccountType]}</span>
            <div>
              <p className="font-semibold text-sm">{account.name}</p>
              <p className="text-[11px] text-muted-foreground uppercase tracking-wide">
                {account.account_type} · {account.currency}
              </p>
            </div>
          </div>
          <div className="flex gap-1">
            <button
              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => onEdit(account)}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
              onClick={() => onDelete(account.id)}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="mt-3">
          <p className={`text-xl font-bold ${isPositive ? 'text-success' : 'text-destructive'}`}>
            {formatMoney(account.current_balance, account.currency)}
          </p>
          {(account.total_income !== undefined || account.total_spent !== undefined) && (
            <div className="flex gap-3 mt-1">
              <span className="text-xs text-success flex items-center gap-0.5">
                <TrendingUp className="w-3 h-3" />
                {formatMoney(account.total_income ?? 0, account.currency)}
              </span>
              <span className="text-xs text-destructive flex items-center gap-0.5">
                <TrendingDown className="w-3 h-3" />
                {formatMoney(account.total_spent ?? 0, account.currency)}
              </span>
            </div>
          )}
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}

type FormState = {
  name: string;
  account_type: AccountType;
  currency: string;
  initial_balance: string;
  color: string;
};

const DEFAULT_FORM: FormState = {
  name: '',
  account_type: 'BANK',
  currency: 'INR',
  initial_balance: '0',
  color: ACCENT_COLORS[0],
};

export default function AccountsOverviewPage() {
  const [overview, setOverview] = useState<AccountsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<FinancialAccount | null>(null);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getAccountsOverview();
      setOverview(data);
    } catch {
      toast({ title: 'Failed to load accounts', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { reload(); }, [reload]);

  const openCreate = () => {
    setEditTarget(null);
    setForm(DEFAULT_FORM);
    setShowForm(true);
  };

  const openEdit = (account: FinancialAccount) => {
    setEditTarget(account);
    setForm({
      name: account.name,
      account_type: account.account_type,
      currency: account.currency,
      initial_balance: String(account.initial_balance),
      color: account.color || ACCENT_COLORS[0],
    });
    setShowForm(true);
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      toast({ title: 'Name is required', variant: 'destructive' });
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        account_type: form.account_type,
        currency: form.currency,
        initial_balance: parseFloat(form.initial_balance) || 0,
        color: form.color,
      };
      if (editTarget) {
        await updateAccount(editTarget.id, payload);
        toast({ title: 'Account updated' });
      } else {
        await createAccount(payload);
        toast({ title: 'Account created' });
      }
      setShowForm(false);
      await reload();
    } catch {
      toast({ title: 'Save failed', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id);
      toast({ title: 'Account removed' });
      await reload();
    } catch {
      toast({ title: 'Delete failed', variant: 'destructive' });
    }
  };

  const netPositive = (overview?.net_flow ?? 0) >= 0;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wallet className="w-6 h-6 text-primary" />
            Accounts
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            All your financial accounts in one view
          </p>
        </div>
        <Button variant="hero" size="sm" onClick={openCreate}>
          <PlusCircle className="w-4 h-4 mr-1" />
          Add Account
        </Button>
      </div>

      {/* Summary strip */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Total Balance', value: overview.total_balance, positive: overview.total_balance >= 0 },
            { label: 'Total Income', value: overview.total_income, positive: true },
            { label: 'Total Spent', value: overview.total_spent, positive: false, invert: true },
            { label: 'Net Flow', value: overview.net_flow, positive: netPositive },
          ].map(({ label, value, positive, invert }) => (
            <FinancialCard key={label}>
              <FinancialCardContent className="pt-3 pb-3">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className={`text-lg font-bold ${invert ? 'text-destructive' : positive ? 'text-success' : 'text-destructive'}`}>
                  {formatMoney(value, 'INR')}
                </p>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      )}

      {loading ? (
        <p className="text-muted-foreground text-center py-12">Loading accounts...</p>
      ) : !overview || overview.accounts.length === 0 ? (
        <div className="text-center py-16 space-y-2">
          <Wallet className="w-10 h-10 mx-auto text-muted-foreground" />
          <p className="text-muted-foreground">No accounts yet. Add your first account to get started.</p>
        </div>
      ) : (
        <>
          {/* Account cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {overview.accounts.map((acct) => (
              <AccountCard key={acct.id} account={acct} onEdit={openEdit} onDelete={handleDelete} />
            ))}
          </div>

          {/* Recent transactions */}
          {overview.recent_transactions.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Recent Transactions</FinancialCardTitle>
                <FinancialCardDescription>Last 10 across all accounts</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent className="space-y-2">
                {overview.recent_transactions.map((txn) => {
                  const acct = overview.accounts.find((a) => a.id === txn.account_id);
                  const isIncome = txn.expense_type === 'INCOME';
                  return (
                    <div key={txn.id} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block w-2 h-2 rounded-full"
                          style={{ backgroundColor: acct?.color || '#6366f1' }}
                        />
                        <span className="text-muted-foreground">{acct?.name ?? 'Unknown'}</span>
                        {txn.notes && <span className="text-foreground">{txn.notes}</span>}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={isIncome ? 'text-success' : 'text-destructive'}>
                          {isIncome ? '+' : '-'}{formatMoney(txn.amount, txn.currency)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {txn.spent_at ? new Date(txn.spent_at).toLocaleDateString() : ''}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </FinancialCardContent>
            </FinancialCard>
          )}
        </>
      )}

      {/* Create/Edit form overlay */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-background border border-border shadow-xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editTarget ? 'Edit Account' : 'New Account'}
              </h2>
              <button onClick={() => setShowForm(false)}>
                <X className="w-5 h-5 text-muted-foreground hover:text-foreground" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Name</label>
                <input
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. HDFC Savings"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Type</label>
                  <select
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    value={form.account_type}
                    onChange={(e) => setForm((f) => ({ ...f, account_type: e.target.value as AccountType }))}
                  >
                    {ACCOUNT_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Currency</label>
                  <input
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary uppercase"
                    value={form.currency}
                    onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value.toUpperCase() }))}
                    maxLength={5}
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground">Initial Balance</label>
                <input
                  type="number"
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={form.initial_balance}
                  onChange={(e) => setForm((f) => ({ ...f, initial_balance: e.target.value }))}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground">Accent Color</label>
                <div className="mt-1 flex flex-wrap gap-2">
                  {ACCENT_COLORS.map((c) => (
                    <button
                      key={c}
                      className="w-6 h-6 rounded-full border-2 transition-transform hover:scale-110"
                      style={{
                        backgroundColor: c,
                        borderColor: form.color === c ? '#fff' : 'transparent',
                        outline: form.color === c ? `2px solid ${c}` : 'none',
                      }}
                      onClick={() => setForm((f) => ({ ...f, color: c }))}
                    >
                      {form.color === c && <Check className="w-3 h-3 text-white mx-auto" />}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
              <Button variant="hero" size="sm" className="flex-1" onClick={() => { void handleSubmit(); }} disabled={saving}>
                {saving ? 'Saving...' : editTarget ? 'Update' : 'Create'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
