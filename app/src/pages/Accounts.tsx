import { useCallback, useEffect, useState } from 'react';
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
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import {
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  getAccountOverview,
  type Account,
  type AccountType,
  type AccountOverview,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';
import {
  Wallet,
  Building2,
  CreditCard,
  Banknote,
  PiggyBank,
  CircleDot,
  Plus,
  Pencil,
  Trash2,
  TrendingUp,
} from 'lucide-react';

const ACCOUNT_TYPE_OPTIONS: { value: AccountType; label: string }[] = [
  { value: 'CHECKING', label: 'Checking' },
  { value: 'SAVINGS', label: 'Savings' },
  { value: 'CREDIT_CARD', label: 'Credit Card' },
  { value: 'WALLET', label: 'Wallet' },
  { value: 'CASH', label: 'Cash' },
  { value: 'OTHER', label: 'Other' },
];

const COLOR_OPTIONS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#94a3b8',
];

function accountTypeIcon(type: string) {
  switch (type) {
    case 'CHECKING': return <Building2 className="w-5 h-5" />;
    case 'SAVINGS': return <PiggyBank className="w-5 h-5" />;
    case 'CREDIT_CARD': return <CreditCard className="w-5 h-5" />;
    case 'WALLET': return <Wallet className="w-5 h-5" />;
    case 'CASH': return <Banknote className="w-5 h-5" />;
    default: return <CircleDot className="w-5 h-5" />;
  }
}

function accountTypeLabel(type: string): string {
  return ACCOUNT_TYPE_OPTIONS.find(o => o.value === type)?.label || type;
}

export default function Accounts() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('CHECKING');
  const [currency, setCurrency] = useState('INR');
  const [balance, setBalance] = useState('0');
  const [color, setColor] = useState('#3b82f6');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [accts, ov] = await Promise.all([listAccounts(), getAccountOverview()]);
      setAccounts(accts);
      setOverview(ov);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load accounts';
      setError(msg);
      toast({ title: 'Failed to load accounts', description: msg });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function resetForm() {
    setName('');
    setAccountType('CHECKING');
    setCurrency('INR');
    setBalance('0');
    setColor('#3b82f6');
    setEditing(null);
  }

  function openCreate() {
    resetForm();
    setOpen(true);
  }

  function openEdit(acct: Account) {
    setEditing(acct);
    setName(acct.name);
    setAccountType(acct.account_type);
    setCurrency(acct.currency);
    setBalance(String(acct.balance));
    setColor(acct.color || '#3b82f6');
    setOpen(true);
  }

  async function onSubmit() {
    if (!name.trim()) {
      setError('Account name is required');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        await updateAccount(editing.id, {
          name: name.trim(),
          account_type: accountType,
          currency,
          balance: Number(balance),
          color,
        });
        toast({ title: 'Account updated' });
      } else {
        await createAccount({
          name: name.trim(),
          account_type: accountType,
          currency,
          balance: Number(balance),
          color,
        });
        toast({ title: 'Account created' });
      }
      setOpen(false);
      resetForm();
      await refresh();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save account';
      setError(msg);
      toast({ title: 'Failed to save account', description: msg });
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
      const msg = err instanceof Error ? err.message : 'Failed to delete account';
      toast({ title: 'Failed to delete account', description: msg });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Accounts</h1>
            <p className="page-subtitle">Manage your financial accounts and track balances.</p>
          </div>
          <Button variant="financial" size="sm" onClick={openCreate}>
            <Plus className="w-4 h-4" />
            Add Account
          </Button>
        </div>
      </div>

      {error && <div className="error mb-4">{error}</div>}

      {/* Net Worth Overview */}
      {overview && (
        <div className="grid gap-4 md:grid-cols-3 mb-6">
          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Net Worth</FinancialCardTitle>
                <TrendingUp className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground">{loading ? '...' : formatMoney(overview.total_balance)}</div>
              <div className="text-sm text-muted-foreground mt-1">Across {overview.account_count} account(s)</div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Active Accounts</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground">{overview.account_count}</div>
              <div className="text-sm text-muted-foreground mt-1">
                {ACCOUNT_TYPE_OPTIONS.filter(t =>
                  accounts.some(a => a.account_type === t.value)
                ).map(t => t.label).join(', ') || 'No accounts yet'}
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Highest Balance</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              {accounts.length > 0 ? (
                <>
                  <div className="metric-value text-foreground">
                    {formatMoney(Math.max(...accounts.map(a => a.balance)))}
                  </div>
                  <div className="text-sm text-muted-foreground mt-1">
                    {accounts.reduce((max, a) => a.balance > max.balance ? a : max, accounts[0]).name}
                  </div>
                </>
              ) : (
                <div className="text-sm text-muted-foreground">No accounts yet</div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Account Cards */}
      {loading ? (
        <div className="card p-8 text-center text-muted-foreground">Loading accounts...</div>
      ) : accounts.length === 0 ? (
        <div className="card p-8 text-center">
          <Wallet className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No accounts yet</h3>
          <p className="text-muted-foreground mb-4">Add your first account to start tracking balances across banks, wallets, and cards.</p>
          <Button variant="financial" onClick={openCreate}>
            <Plus className="w-4 h-4" />
            Add Your First Account
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {accounts.map((acct) => (
            <FinancialCard
              key={acct.id}
              variant="financial"
              className="group card-interactive fade-in-up"
            >
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center text-white"
                      style={{ backgroundColor: acct.color || '#3b82f6' }}
                    >
                      {accountTypeIcon(acct.account_type)}
                    </div>
                    <div>
                      <FinancialCardTitle className="text-sm font-semibold">{acct.name}</FinancialCardTitle>
                      <div className="text-xs text-muted-foreground">{accountTypeLabel(acct.account_type)}</div>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(acct)}>
                      <Pencil className="w-3.5 h-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => onDelete(acct.id)}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground">{formatMoney(acct.balance, acct.currency)}</div>
                <div className="text-xs text-muted-foreground mt-1">{acct.currency}</div>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Account' : 'New Account'}</DialogTitle>
            <DialogDescription>
              {editing ? 'Update your account details.' : 'Add a new financial account to track.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="acct-name">Account Name</Label>
              <Input
                id="acct-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., HDFC Savings"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="acct-type">Type</Label>
                <select
                  id="acct-type"
                  className="input"
                  value={accountType}
                  onChange={(e) => setAccountType(e.target.value as AccountType)}
                >
                  {ACCOUNT_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="acct-currency">Currency</Label>
                <Input
                  id="acct-currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  placeholder="INR"
                  maxLength={10}
                />
              </div>
            </div>
            <div>
              <Label htmlFor="acct-balance">Initial Balance</Label>
              <Input
                id="acct-balance"
                type="number"
                step="0.01"
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
              />
            </div>
            <div>
              <Label>Color</Label>
              <div className="flex gap-2 flex-wrap mt-1">
                {COLOR_OPTIONS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`w-8 h-8 rounded-full border-2 transition-all ${
                      color === c ? 'border-foreground scale-110' : 'border-transparent'
                    }`}
                    style={{ backgroundColor: c }}
                    onClick={() => setColor(c)}
                    aria-label={`Color ${c}`}
                  />
                ))}
              </div>
            </div>
          </div>
          {error && <div className="error mt-2">{error}</div>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={onSubmit} disabled={saving}>
              {editing ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
