import { useState, useEffect, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Plus,
  Landmark,
  CreditCard,
  TrendingUp,
  Wallet,
  Banknote,
  Pencil,
  Trash2,
  Building2,
  DollarSign,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  getAccountsOverview,
  type Account,
  type AccountCreate,
  type AccountType,
  type AccountsOverview as OverviewData,
} from '@/api/accounts';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
} from '@/components/ui/alert-dailog';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPE_OPTIONS: { value: AccountType; label: string }[] = [
  { value: 'BANK', label: 'Bank' },
  { value: 'CREDIT', label: 'Credit Card' },
  { value: 'INVESTMENT', label: 'Investment' },
  { value: 'CASH', label: 'Cash' },
];

const COLOR_OPTIONS = [
  '#3B82F6', // blue
  '#10B981', // emerald
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // violet
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#F97316', // orange
];

function AccountTypeIcon({ type, className }: { type: string; className?: string }) {
  const cls = className || 'w-6 h-6';
  switch (type) {
    case 'CREDIT':
      return <CreditCard className={cls} />;
    case 'INVESTMENT':
      return <TrendingUp className={cls} />;
    case 'CASH':
      return <Banknote className={cls} />;
    default:
      return <Landmark className={cls} />;
  }
}

function AccountTypeLabel({ type }: { type: string }) {
  const labels: Record<string, string> = {
    BANK: 'Bank Account',
    CREDIT: 'Credit Card',
    INVESTMENT: 'Investment',
    CASH: 'Cash',
  };
  return <>{labels[type] || type}</>;
}

export default function AccountsOverview() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);

  // Create/Edit modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<AccountType>('BANK');
  const [formInstitution, setFormInstitution] = useState('');
  const [formBalance, setFormBalance] = useState('');
  const [formColor, setFormColor] = useState('#3B82F6');
  const [saving, setSaving] = useState(false);

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [accountsData, overviewData] = await Promise.all([
        listAccounts({ include_inactive: showInactive }),
        getAccountsOverview(),
      ]);
      setAccounts(accountsData);
      setOverview(overviewData);
    } catch (error: unknown) {
      toast({ title: 'Failed to load accounts', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }, [toast, showInactive]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function openCreate() {
    setEditingAccount(null);
    setFormName('');
    setFormType('BANK');
    setFormInstitution('');
    setFormBalance('');
    setFormColor('#3B82F6');
    setModalOpen(true);
  }

  function openEdit(account: Account) {
    setEditingAccount(account);
    setFormName(account.name);
    setFormType(account.account_type);
    setFormInstitution(account.institution || '');
    setFormBalance(String(account.balance));
    setFormColor(account.color);
    setModalOpen(true);
  }

  async function onSave() {
    if (!formName.trim()) return;
    setSaving(true);
    try {
      if (editingAccount) {
        await updateAccount(editingAccount.id, {
          name: formName.trim(),
          account_type: formType,
          institution: formInstitution.trim() || undefined,
          balance: formBalance ? Number(formBalance) : undefined,
          color: formColor,
        });
        toast({ title: 'Account updated' });
      } else {
        const payload: AccountCreate = {
          name: formName.trim(),
          account_type: formType,
          color: formColor,
        };
        if (formInstitution.trim()) payload.institution = formInstitution.trim();
        if (formBalance) payload.balance = Number(formBalance);
        await createAccount(payload);
        toast({ title: 'Account added' });
      }
      setModalOpen(false);
      await refresh();
    } catch (error: unknown) {
      toast({ title: 'Failed to save account', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  // Compute type breakdown percentages for chart
  const typeBreakdown = overview?.type_breakdown || [];
  const totalForChart = typeBreakdown.reduce((s, t) => s + Math.abs(t.total), 0);

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Accounts Overview</h1>
            <p className="page-subtitle">View all your financial accounts in one place</p>
          </div>
          <div className="flex gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowInactive((v) => !v)}
            >
              {showInactive ? 'Hide Inactive' : 'Show Inactive'}
            </Button>
            <Button variant="financial" size="sm" onClick={openCreate}>
              <Plus className="w-4 h-4" />
              Add Account
            </Button>
          </div>
        </div>
      </div>

      {/* Net Worth & Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Net Worth
              </FinancialCardTitle>
              <DollarSign className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {formatMoney(overview?.net_worth || 0)}
            </div>
            <div className="text-sm text-muted-foreground">
              across {overview?.account_count || 0} account{(overview?.account_count || 0) !== 1 ? 's' : ''}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Assets
              </FinancialCardTitle>
              <ArrowUpRight className="w-5 h-5 text-green-500" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-green-600 mb-1">
              {formatMoney(overview?.total_assets || 0)}
            </div>
            <div className="text-sm text-muted-foreground">
              Bank, Investment & Cash
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Liabilities
              </FinancialCardTitle>
              <ArrowDownRight className="w-5 h-5 text-red-500" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-red-600 mb-1">
              {formatMoney(overview?.total_liabilities || 0)}
            </div>
            <div className="text-sm text-muted-foreground">
              Credit cards & loans
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Balance
              </FinancialCardTitle>
              <Wallet className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {formatMoney(overview?.total_balance || 0)}
            </div>
            <div className="text-sm text-muted-foreground">
              All accounts combined
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Type Breakdown */}
      {typeBreakdown.length > 0 && (
        <FinancialCard variant="financial" className="mb-8">
          <FinancialCardHeader>
            <FinancialCardTitle className="text-base">Balance by Account Type</FinancialCardTitle>
            <FinancialCardDescription>Distribution of your finances across account types</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-4">
              {typeBreakdown.map((item) => {
                const pct = totalForChart > 0 ? Math.round((Math.abs(item.total) / totalForChart) * 100) : 0;
                const typeColor = item.accounts[0]?.color || '#3B82F6';
                return (
                  <div key={item.type} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: typeColor }}
                        />
                        <AccountTypeIcon type={item.type} className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium">
                          <AccountTypeLabel type={item.type} />
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {item.count} account{item.count !== 1 ? 's' : ''}
                        </Badge>
                      </div>
                      <span className="text-sm font-semibold">
                        {formatMoney(item.total)}
                      </span>
                    </div>
                    <Progress value={pct} className="h-2" />
                  </div>
                );
              })}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Account Cards */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <div className="col-span-full text-center py-12 text-muted-foreground">Loading...</div>
        ) : accounts.length === 0 ? (
          <div className="col-span-full">
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardContent className="text-center py-12">
                <Landmark className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                <h3 className="text-lg font-semibold mb-2">No accounts yet</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Add your bank accounts, credit cards, and investments to get a complete financial overview.
                </p>
                <Button variant="financial" onClick={openCreate}>
                  <Plus className="w-4 h-4" />
                  Add Your First Account
                </Button>
              </FinancialCardContent>
            </FinancialCard>
          </div>
        ) : (
          accounts.map((account) => (
            <FinancialCard
              key={account.id}
              variant="financial"
              className="fade-in-up"
            >
              <FinancialCardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center"
                      style={{ backgroundColor: account.color + '20', color: account.color }}
                    >
                      <AccountTypeIcon type={account.account_type} className="w-5 h-5" />
                    </div>
                    <div>
                      <FinancialCardTitle className="text-base">{account.name}</FinancialCardTitle>
                      <FinancialCardDescription className="text-xs">
                        {account.institution ? (
                          <span className="flex items-center gap-1">
                            <Building2 className="w-3 h-3" />
                            {account.institution}
                          </span>
                        ) : (
                          <AccountTypeLabel type={account.account_type} />
                        )}
                      </FinancialCardDescription>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => openEdit(account)}>
                      <Pencil className="w-3.5 h-3.5" />
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete account?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will permanently delete &quot;{account.name}&quot;. Transactions linked to this account will be unlinked.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={async () => {
                              try {
                                await deleteAccount(account.id);
                                await refresh();
                                toast({ title: 'Account deleted' });
                              } catch (error: unknown) {
                                toast({
                                  title: 'Delete failed',
                                  description: getErrorMessage(error, 'Please try again.'),
                                });
                              }
                            }}
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-bold">
                      {formatMoney(account.balance, account.currency)}
                    </span>
                    <Badge
                      variant="outline"
                      className={
                        account.account_type === 'CREDIT'
                          ? 'text-xs bg-red-50 text-red-700 border-red-200'
                          : 'text-xs bg-green-50 text-green-700 border-green-200'
                      }
                    >
                      {account.account_type === 'CREDIT' ? 'Liability' : 'Asset'}
                    </Badge>
                  </div>
                  {!account.active && (
                    <Badge variant="outline" className="text-xs bg-gray-100 text-gray-500">
                      Inactive
                    </Badge>
                  )}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ))
        )}
      </div>

      {/* Create/Edit Account Dialog */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingAccount ? 'Edit Account' : 'Add Account'}</DialogTitle>
            <DialogDescription>
              {editingAccount
                ? 'Update your account details.'
                : 'Add a financial account to track your overall finances.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm mb-1">Account Name</label>
              <input
                className="input w-full"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. Main Checking, Visa Card, Brokerage"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm mb-1">Account Type</label>
                <select
                  className="input w-full"
                  value={formType}
                  onChange={(e) => setFormType(e.target.value as AccountType)}
                >
                  {ACCOUNT_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm mb-1">Balance</label>
                <input
                  className="input w-full"
                  type="number"
                  step="0.01"
                  value={formBalance}
                  onChange={(e) => setFormBalance(e.target.value)}
                  placeholder="0.00"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm mb-1">Institution (optional)</label>
              <input
                className="input w-full"
                value={formInstitution}
                onChange={(e) => setFormInstitution(e.target.value)}
                placeholder="e.g. Chase, Vanguard, PayPal"
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Color</label>
              <div className="flex gap-2">
                {COLOR_OPTIONS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`w-8 h-8 rounded-full border-2 transition ${
                      formColor === c ? 'border-foreground scale-110' : 'border-transparent hover:border-muted-foreground'
                    }`}
                    style={{ backgroundColor: c }}
                    onClick={() => setFormColor(c)}
                  />
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={saving || !formName.trim()}>
              {editingAccount ? 'Update' : 'Add Account'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
