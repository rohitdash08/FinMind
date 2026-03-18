import { useEffect, useState } from 'react';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Plus,
  Pencil,
  Trash2,
  Building2,
  Wallet,
  CreditCard,
  TrendingUp,
  Banknote,
  MoreHorizontal,
} from 'lucide-react';
import {
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  ACCOUNT_TYPE_LABELS,
  type FinancialAccount,
  type AccountType,
  type CreateAccountPayload,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPE_ICONS: Record<AccountType, React.ElementType> = {
  CHECKING: Wallet,
  SAVINGS: Building2,
  CREDIT: CreditCard,
  INVESTMENT: TrendingUp,
  CASH: Banknote,
  OTHER: MoreHorizontal,
};

const ACCOUNT_TYPES: AccountType[] = ['CHECKING', 'SAVINGS', 'CREDIT', 'INVESTMENT', 'CASH', 'OTHER'];

const EMPTY_FORM: CreateAccountPayload = {
  name: '',
  account_type: 'CHECKING',
  balance: 0,
  institution: '',
  currency: 'INR',
};

export function Accounts() {
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<FinancialAccount | null>(null);
  const [form, setForm] = useState<CreateAccountPayload>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAccounts();
      setAccounts(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const openCreate = () => {
    setEditingAccount(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (account: FinancialAccount) => {
    setEditingAccount(account);
    setForm({
      name: account.name,
      account_type: account.account_type,
      balance: account.balance,
      institution: account.institution ?? '',
      currency: account.currency,
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      if (editingAccount) {
        await updateAccount(editingAccount.id, form);
      } else {
        await createAccount(form);
      }
      setDialogOpen(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save account');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    setDeleteId(id);
    try {
      await deleteAccount(id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to delete account');
    } finally {
      setDeleteId(null);
    }
  };

  const totalAssets = accounts
    .filter(a => a.account_type !== 'CREDIT')
    .reduce((sum, a) => sum + a.balance, 0);
  const totalCredit = accounts
    .filter(a => a.account_type === 'CREDIT')
    .reduce((sum, a) => sum + a.balance, 0);
  const netWorth = totalAssets - totalCredit;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Financial Accounts</h1>
            <p className="page-subtitle">Manage your bank accounts, credit cards, and investments.</p>
          </div>
          <Button variant="financial" size="sm" onClick={openCreate}>
            <Plus className="w-4 h-4" />
            Add Account
          </Button>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      {/* Summary row */}
      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Net Worth</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className={`metric-value ${netWorth >= 0 ? 'text-success' : 'text-destructive'}`}>
              {loading ? '...' : formatMoney(netWorth)}
            </div>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Assets</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground">{loading ? '...' : formatMoney(totalAssets)}</div>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Credit Debt</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-destructive">{loading ? '...' : formatMoney(totalCredit)}</div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Account list */}
      <FinancialCard variant="financial" className="fade-in-up">
        <FinancialCardHeader>
          <FinancialCardTitle className="section-title">Your Accounts</FinancialCardTitle>
          <FinancialCardDescription>{accounts.length} active account{accounts.length !== 1 ? 's' : ''}</FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          {loading ? (
            <div className="text-sm text-muted-foreground">Loading accounts…</div>
          ) : accounts.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-muted-foreground mb-4">No accounts yet. Add your first account to get started.</p>
              <Button variant="financial" onClick={openCreate}>
                <Plus className="w-4 h-4" />
                Add Account
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {accounts.map((account) => {
                const Icon = ACCOUNT_TYPE_ICONS[account.account_type];
                const isCredit = account.account_type === 'CREDIT';
                return (
                  <div
                    key={account.id}
                    className="interactive-row flex items-center justify-between gap-4"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isCredit
                          ? 'bg-destructive-light text-destructive'
                          : 'bg-success-light text-success'
                      }`}>
                        <Icon className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <div className="font-medium text-foreground truncate">{account.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {ACCOUNT_TYPE_LABELS[account.account_type]}
                          {account.institution ? ` · ${account.institution}` : ''}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      <div className={`text-right font-semibold ${isCredit ? 'text-destructive' : 'text-foreground'}`}>
                        {isCredit ? '-' : ''}{formatMoney(account.balance, account.currency)}
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => openEdit(account)}
                        aria-label={`Edit ${account.name}`}
                      >
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive hover:text-destructive"
                        onClick={() => void handleDelete(account.id)}
                        disabled={deleteId === account.id}
                        aria-label={`Delete ${account.name}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>{editingAccount ? 'Edit Account' : 'Add Account'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label htmlFor="acc-name">Account Name</Label>
              <Input
                id="acc-name"
                placeholder="e.g. HDFC Savings, Chase Checking"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="acc-type">Account Type</Label>
              <Select
                value={form.account_type}
                onValueChange={v => setForm(f => ({ ...f, account_type: v as AccountType }))}
              >
                <SelectTrigger id="acc-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ACCOUNT_TYPES.map(t => (
                    <SelectItem key={t} value={t}>{ACCOUNT_TYPE_LABELS[t]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label htmlFor="acc-balance">Balance</Label>
                <Input
                  id="acc-balance"
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={form.balance}
                  onChange={e => setForm(f => ({ ...f, balance: parseFloat(e.target.value) || 0 }))}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="acc-currency">Currency</Label>
                <Input
                  id="acc-currency"
                  placeholder="INR"
                  maxLength={10}
                  value={form.currency ?? 'INR'}
                  onChange={e => setForm(f => ({ ...f, currency: e.target.value.toUpperCase() }))}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="acc-institution">Institution (optional)</Label>
              <Input
                id="acc-institution"
                placeholder="e.g. HDFC Bank, Chase, Vanguard"
                value={form.institution ?? ''}
                onChange={e => setForm(f => ({ ...f, institution: e.target.value }))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button variant="financial" onClick={() => void handleSave()} disabled={saving || !form.name.trim()}>
              {saving ? 'Saving…' : editingAccount ? 'Save Changes' : 'Add Account'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
