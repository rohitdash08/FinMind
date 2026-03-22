import { useEffect, useState, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import {
  Wallet,
  PiggyBank,
  CreditCard,
  TrendingUp,
  Landmark,
  Banknote,
  Plus,
  Pencil,
  Trash2,
  RefreshCw,
  X,
} from 'lucide-react';
import {
  getAccounts,
  getAccountSummary,
  createAccount,
  updateAccount,
  deleteAccount,
  type FinancialAccount,
  type AccountSummary,
  type CreateAccountPayload,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPE_META: Record<
  FinancialAccount['type'],
  { label: string; icon: typeof Wallet; color: string; bg: string; isLiability: boolean }
> = {
  CHECKING: { label: 'Checking', icon: Wallet, color: 'text-primary', bg: 'bg-primary/10', isLiability: false },
  SAVINGS: { label: 'Savings', icon: PiggyBank, color: 'text-success', bg: 'bg-success/10', isLiability: false },
  CREDIT_CARD: { label: 'Credit Card', icon: CreditCard, color: 'text-destructive', bg: 'bg-destructive/10', isLiability: true },
  INVESTMENT: { label: 'Investment', icon: TrendingUp, color: 'text-accent-foreground', bg: 'bg-accent/10', isLiability: false },
  LOAN: { label: 'Loan', icon: Landmark, color: 'text-warning', bg: 'bg-warning/10', isLiability: true },
  CASH: { label: 'Cash', icon: Banknote, color: 'text-foreground', bg: 'bg-muted', isLiability: false },
};

const ACCOUNT_TYPES = Object.keys(ACCOUNT_TYPE_META) as FinancialAccount['type'][];

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

type FormState = CreateAccountPayload & { id?: number };
const EMPTY_FORM: FormState = { name: '', type: 'CHECKING', balance: 0, currency: '', institution: '' };

export function Accounts() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [summary, setSummary] = useState<AccountSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [accts, summ] = await Promise.all([getAccounts(), getAccountSummary()]);
      setAccounts(accts);
      setSummary(summ);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load accounts';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      toast({ title: 'Validation', description: 'Account name is required.' });
      return;
    }
    setSaving(true);
    try {
      const payload: CreateAccountPayload = {
        name: form.name.trim(),
        type: form.type,
        balance: Number(form.balance) || 0,
        ...(form.institution ? { institution: form.institution.trim() } : {}),
        ...(form.currency ? { currency: form.currency } : {}),
      };
      if (form.id) {
        await updateAccount(form.id, payload);
        toast({ title: 'Account updated' });
      } else {
        await createAccount(payload);
        toast({ title: 'Account created' });
      }
      setShowForm(false);
      setForm(EMPTY_FORM);
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save account';
      toast({ title: 'Error', description: msg });
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (acct: FinancialAccount) => {
    setForm({
      id: acct.id,
      name: acct.name,
      type: acct.type,
      balance: acct.balance,
      currency: acct.currency,
      institution: acct.institution,
    });
    setShowForm(true);
  };

  const handleDelete = async (acct: FinancialAccount) => {
    try {
      await deleteAccount(acct.id);
      toast({ title: 'Account deleted', description: acct.name });
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete account';
      toast({ title: 'Error', description: msg });
    }
  };

  const grouped = ACCOUNT_TYPES.reduce<Record<string, FinancialAccount[]>>((acc, type) => {
    const matching = accounts.filter((a) => a.type === type);
    if (matching.length > 0) acc[type] = matching;
    return acc;
  }, {});

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Financial Accounts</h1>
            <p className="page-subtitle">
              Unified view of all your accounts across institutions.
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
              <RefreshCw className={"w-4 h-4" + (loading ? ' animate-spin' : '')} />
              Refresh
            </Button>
            <Button
              variant="financial"
              size="sm"
              onClick={() => { setForm(EMPTY_FORM); setShowForm(true); }}
            >
              <Plus className="w-4 h-4" />
              Add Account
            </Button>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}. Showing empty fallback state.</div>}

      {/* Summary cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-3 mb-8">
          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Assets
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-success">
                {loading ? '...' : currency(summary.total_assets, summary.currency)}
              </div>
              <p className="text-sm text-muted-foreground mt-1">Checking + Savings + Investments + Cash</p>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Liabilities
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-destructive">
                {loading ? '...' : currency(summary.total_liabilities, summary.currency)}
              </div>
              <p className="text-sm text-muted-foreground mt-1">Credit Cards + Loans</p>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Net Worth
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className={"metric-value " + (summary.net_worth >= 0 ? 'text-foreground' : 'text-destructive')}>
                {loading ? '...' : currency(summary.net_worth, summary.currency)}
              </div>
              <p className="text-sm text-muted-foreground mt-1">Assets minus Liabilities</p>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Add/Edit form */}
      {showForm && (
        <div className="card mb-8 p-6 fade-in-up">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">{form.id ? 'Edit Account' : 'New Account'}</h2>
            <Button variant="ghost" size="icon" onClick={() => { setShowForm(false); setForm(EMPTY_FORM); }}>
              <X className="w-4 h-4" />
            </Button>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="acct-name">Account Name</Label>
              <input
                id="acct-name"
                className="input"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="e.g. Chase Checking"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="acct-type">Type</Label>
              <select
                id="acct-type"
                className="input"
                value={form.type}
                onChange={(e) => setForm((p) => ({ ...p, type: e.target.value as FinancialAccount['type'] }))}
              >
                {ACCOUNT_TYPES.map((t) => (
                  <option key={t} value={t}>{ACCOUNT_TYPE_META[t].label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="acct-balance">Current Balance</Label>
              <input
                id="acct-balance"
                type="number"
                step="0.01"
                className="input"
                value={form.balance}
                onChange={(e) => setForm((p) => ({ ...p, balance: parseFloat(e.target.value) || 0 }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="acct-institution">Institution</Label>
              <input
                id="acct-institution"
                className="input"
                value={form.institution || ''}
                onChange={(e) => setForm((p) => ({ ...p, institution: e.target.value }))}
                placeholder="e.g. Chase, Fidelity"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <Button variant="outline" size="sm" onClick={() => { setShowForm(false); setForm(EMPTY_FORM); }}>
              Cancel
            </Button>
            <Button variant="financial" size="sm" onClick={() => void handleSubmit()} disabled={saving}>
              {saving ? 'Saving...' : form.id ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      )}

      {/* Grouped account cards */}
      {Object.entries(grouped).length === 0 && !loading && (
        <div className="card p-8 text-center fade-in-up">
          <Wallet className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No accounts yet</h3>
          <p className="text-muted-foreground mb-4">
            Add your financial accounts to get a complete overview of your finances.
          </p>
          <Button variant="financial" onClick={() => { setForm(EMPTY_FORM); setShowForm(true); }}>
            <Plus className="w-4 h-4" />
            Add Your First Account
          </Button>
        </div>
      )}

      {Object.entries(grouped).map(([type, accts]) => {
        const meta = ACCOUNT_TYPE_META[type as FinancialAccount['type']];
        const Icon = meta.icon;
        const groupTotal = accts.reduce((s, a) => s + a.balance, 0);

        return (
          <div key={type} className="mb-8">
            <div className="flex items-center gap-3 mb-4">
              <div className={"w-8 h-8 rounded-lg flex items-center justify-center " + meta.bg}>
                <Icon className={"w-4 h-4 " + meta.color} />
              </div>
              <h2 className="text-lg font-semibold">{meta.label} Accounts</h2>
              <span className="text-sm text-muted-foreground ml-auto">
                Total: {currency(groupTotal, accts[0]?.currency)}
              </span>
            </div>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {accts.map((acct) => (
                <FinancialCard
                  key={acct.id}
                  variant="financial"
                  className="group card-interactive fade-in-up"
                >
                  <FinancialCardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <FinancialCardTitle className="text-sm font-medium">
                        {acct.name}
                      </FinancialCardTitle>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleEdit(acct)}>
                          <Pencil className="w-3 h-3" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => void handleDelete(acct)}>
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </div>
                    </div>
                    {acct.institution && (
                      <FinancialCardDescription>{acct.institution}</FinancialCardDescription>
                    )}
                  </FinancialCardHeader>
                  <FinancialCardContent>
                    <div className={"text-2xl font-bold " + (meta.isLiability ? 'text-destructive' : 'text-foreground')}>
                      {meta.isLiability ? '-' : ''}{currency(Math.abs(acct.balance), acct.currency)}
                    </div>
                  </FinancialCardContent>
                  <FinancialCardFooter className="text-xs text-muted-foreground">
                    {acct.last_synced
                      ? 'Synced ' + new Date(acct.last_synced).toLocaleDateString()
                      : 'Manual entry'}
                  </FinancialCardFooter>
                </FinancialCard>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}