import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  Landmark,
  Plus,
  Wallet,
  CreditCard,
  PiggyBank,
  TrendingUp,
  Building2,
  MoreHorizontal,
  Pencil,
  Trash2,
} from 'lucide-react';
import {
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  getAccountsOverview,
  type FinancialAccount,
  type AccountOverview,
  type AccountCreate,
  type AccountType,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';
import { useToast } from '@/components/ui/use-toast';

const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  CHECKING: 'Checking',
  SAVINGS: 'Savings',
  CREDIT_CARD: 'Credit Card',
  INVESTMENT: 'Investment',
  LOAN: 'Loan',
  OTHER: 'Other',
};

const ACCOUNT_TYPE_ICONS: Record<AccountType, typeof Wallet> = {
  CHECKING: Wallet,
  SAVINGS: PiggyBank,
  CREDIT_CARD: CreditCard,
  INVESTMENT: TrendingUp,
  LOAN: Landmark,
  OTHER: MoreHorizontal,
};

const ACCOUNT_TYPES: AccountType[] = ['CHECKING', 'SAVINGS', 'CREDIT_CARD', 'INVESTMENT', 'LOAN', 'OTHER'];

type FormState = {
  name: string;
  account_type: AccountType;
  institution: string;
  balance: string;
  currency: string;
};

const EMPTY_FORM: FormState = {
  name: '',
  account_type: 'CHECKING',
  institution: '',
  balance: '0',
  currency: '',
};

export function AccountsOverview() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accts, ov] = await Promise.all([listAccounts(), getAccountsOverview()]);
      setAccounts(accts);
      setOverview(ov);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
  }, []);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (account: FinancialAccount) => {
    setEditingId(account.id);
    setForm({
      name: account.name,
      account_type: account.account_type,
      institution: account.institution || '',
      balance: String(account.balance),
      currency: account.currency,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast({ title: 'Validation error', description: 'Account name is required.', variant: 'destructive' });
      return;
    }
    setSubmitting(true);
    try {
      const payload: AccountCreate = {
        name: form.name.trim(),
        account_type: form.account_type,
        institution: form.institution.trim() || undefined,
        balance: parseFloat(form.balance) || 0,
        currency: form.currency || undefined,
      };
      if (editingId) {
        await updateAccount(editingId, payload);
        toast({ title: 'Account updated' });
      } else {
        await createAccount(payload);
        toast({ title: 'Account created' });
      }
      setDialogOpen(false);
      await fetchData();
    } catch (err: unknown) {
      toast({ title: 'Error', description: err instanceof Error ? err.message : 'Failed to save account', variant: 'destructive' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id);
      toast({ title: 'Account deleted' });
      await fetchData();
    } catch (err: unknown) {
      toast({ title: 'Error', description: err instanceof Error ? err.message : 'Failed to delete account', variant: 'destructive' });
    }
  };

  const totalBalance = overview?.total_balance ?? 0;

  // Group accounts by type for display
  const accountsByType = ACCOUNT_TYPES.map((type) => ({
    type,
    label: ACCOUNT_TYPE_LABELS[type],
    Icon: ACCOUNT_TYPE_ICONS[type],
    accounts: accounts.filter((a) => a.account_type === type),
  })).filter((g) => g.accounts.length > 0);

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Accounts Overview</h1>
            <p className="page-subtitle">
              {overview ? `${overview.total_accounts} account(s) across all institutions` : 'Manage your financial accounts'}
            </p>
          </div>
          <Button variant="financial" size="sm" onClick={openCreate}>
            <Plus className="w-4 h-4" />
            Add Account
          </Button>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      {/* Net Worth Card */}
      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="premium" className="md:col-span-1 fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Net Worth</FinancialCardTitle>
              <Wallet className="w-5 h-5 text-primary" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{loading ? '...' : formatMoney(totalBalance)}</div>
            <p className="text-sm text-muted-foreground">Across all active accounts</p>
          </FinancialCardContent>
        </FinancialCard>

        {/* Balance by Type Chart */}
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-3">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">By Account Type</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {!overview || overview.by_type.length === 0 ? (
              <div className="text-sm text-muted-foreground">No accounts yet.</div>
            ) : (
              <div className="space-y-2">
                {overview.by_type.map((group) => {
                  const pct = totalBalance !== 0 ? Math.abs(group.total_balance / totalBalance) * 100 : 0;
                  return (
                    <div key={group.type} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-foreground">{ACCOUNT_TYPE_LABELS[group.type as AccountType]}</span>
                        <span className="text-muted-foreground">{formatMoney(group.total_balance)} ({group.count})</span>
                      </div>
                      <div className="chart-track h-2">
                        <div className="chart-fill-primary h-2" style={{ width: `${Math.max(2, Math.min(100, pct))}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>

        {/* By Institution */}
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-3">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">By Institution</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {!overview || overview.by_institution.length === 0 ? (
              <div className="text-sm text-muted-foreground">No accounts yet.</div>
            ) : (
              <div className="space-y-2">
                {overview.by_institution.map((inst) => (
                  <div key={inst.institution} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-4 h-4 text-muted-foreground" />
                      <span className="text-foreground">{inst.institution}</span>
                    </div>
                    <span className="text-muted-foreground">{formatMoney(inst.total_balance)} ({inst.count})</span>
                  </div>
                ))}
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Account Cards grouped by type */}
      {accounts.length === 0 && !loading && (
        <FinancialCard variant="financial" className="text-center py-12 fade-in-up">
          <FinancialCardContent>
            <Landmark className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">No accounts yet</h3>
            <p className="text-sm text-muted-foreground mb-4">Add your bank accounts, credit cards, and investments to see a unified view.</p>
            <Button variant="financial" onClick={openCreate}>
              <Plus className="w-4 h-4" />
              Add Your First Account
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {accountsByType.map((group) => (
        <div key={group.type} className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <group.Icon className="w-5 h-5 text-primary" />
            <h2 className="section-title">{group.label}</h2>
            <span className="text-sm text-muted-foreground">({group.accounts.length})</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {group.accounts.map((account) => (
              <FinancialCard key={account.id} variant="financial" className="group card-interactive fade-in-up">
                <FinancialCardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <FinancialCardTitle className="text-sm font-medium text-foreground">{account.name}</FinancialCardTitle>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(account)}>
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => void handleDelete(account.id)}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                  {account.institution && (
                    <FinancialCardDescription>{account.institution}</FinancialCardDescription>
                  )}
                </FinancialCardHeader>
                <FinancialCardContent>
                  <div className="metric-value text-foreground">{formatMoney(account.balance, account.currency)}</div>
                  <div className="text-xs text-muted-foreground mt-1">{account.currency}</div>
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>
        </div>
      ))}

      {/* Add/Edit Dialog - using native dialog for simplicity following existing patterns */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setDialogOpen(false)}>
          <div className="bg-background rounded-2xl border shadow-xl w-full max-w-md p-6 mx-4" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4">{editingId ? 'Edit Account' : 'Add Account'}</h2>
            <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
              <div>
                <label htmlFor="account-name" className="text-sm font-medium text-foreground">Name *</label>
                <input
                  id="account-name"
                  className="input mt-1 w-full"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. Chase Checking"
                  required
                />
              </div>
              <div>
                <label htmlFor="account-type" className="text-sm font-medium text-foreground">Type *</label>
                <select
                  id="account-type"
                  className="input mt-1 w-full"
                  value={form.account_type}
                  onChange={(e) => setForm((f) => ({ ...f, account_type: e.target.value as AccountType }))}
                >
                  {ACCOUNT_TYPES.map((t) => (
                    <option key={t} value={t}>{ACCOUNT_TYPE_LABELS[t]}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="account-institution" className="text-sm font-medium text-foreground">Institution</label>
                <input
                  id="account-institution"
                  className="input mt-1 w-full"
                  value={form.institution}
                  onChange={(e) => setForm((f) => ({ ...f, institution: e.target.value }))}
                  placeholder="e.g. Chase, Vanguard"
                />
              </div>
              <div>
                <label htmlFor="account-balance" className="text-sm font-medium text-foreground">Balance</label>
                <input
                  id="account-balance"
                  type="number"
                  step="0.01"
                  className="input mt-1 w-full"
                  value={form.balance}
                  onChange={(e) => setForm((f) => ({ ...f, balance: e.target.value }))}
                />
              </div>
              <div>
                <label htmlFor="account-currency" className="text-sm font-medium text-foreground">Currency</label>
                <input
                  id="account-currency"
                  className="input mt-1 w-full"
                  value={form.currency}
                  onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
                  placeholder="Defaults to your preference"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <Button type="button" variant="outline" className="flex-1" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button type="submit" variant="financial" className="flex-1" disabled={submitting}>
                  {submitting ? 'Saving...' : editingId ? 'Update' : 'Add Account'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
