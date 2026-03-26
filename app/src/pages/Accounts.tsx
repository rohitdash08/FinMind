import { useEffect, useState, useMemo, useCallback } from 'react';
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
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  CreditCard,
  DollarSign,
  Landmark,
  LineChart,
  Plus,
  TrendingDown,
  TrendingUp,
  Wallet,
  Banknote,
  PiggyBank,
  RefreshCw,
  Trash2,
  Edit3,
} from 'lucide-react';
import {
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  getAccountsOverview,
  type FinancialAccount,
  type AccountCreate,
  type AccountsOverview,
  type AccountType,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  CHECKING: 'Checking',
  SAVINGS: 'Savings',
  CREDIT_CARD: 'Credit Card',
  INVESTMENT: 'Investment',
  LOAN: 'Loan',
  CASH: 'Cash',
  OTHER: 'Other',
};

const ACCOUNT_TYPE_ICONS: Record<AccountType, typeof Wallet> = {
  CHECKING: Landmark,
  SAVINGS: PiggyBank,
  CREDIT_CARD: CreditCard,
  INVESTMENT: LineChart,
  LOAN: Banknote,
  CASH: DollarSign,
  OTHER: Wallet,
};

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

export function Accounts() {
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [overview, setOverview] = useState<AccountsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<FinancialAccount | null>(null);

  // Form state
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<AccountType>('CHECKING');
  const [formInstitution, setFormInstitution] = useState('');
  const [formBalance, setFormBalance] = useState('');
  const [formCurrency, setFormCurrency] = useState('INR');
  const [formNotes, setFormNotes] = useState('');
  const [formSubmitting, setFormSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [accts, ov] = await Promise.all([
        listAccounts(),
        getAccountsOverview(month),
      ]);
      setAccounts(accts);
      setOverview(ov);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const resetForm = () => {
    setFormName('');
    setFormType('CHECKING');
    setFormInstitution('');
    setFormBalance('');
    setFormCurrency('INR');
    setFormNotes('');
    setEditingAccount(null);
  };

  const openCreateDialog = () => {
    resetForm();
    setDialogOpen(true);
  };

  const openEditDialog = (acct: FinancialAccount) => {
    setEditingAccount(acct);
    setFormName(acct.name);
    setFormType(acct.account_type);
    setFormInstitution(acct.institution || '');
    setFormBalance(String(acct.balance));
    setFormCurrency(acct.currency);
    setFormNotes(acct.notes || '');
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    if (!formName.trim()) return;
    setFormSubmitting(true);
    try {
      if (editingAccount) {
        await updateAccount(editingAccount.id, {
          name: formName,
          account_type: formType,
          institution: formInstitution || undefined,
          balance: parseFloat(formBalance) || 0,
          currency: formCurrency,
          notes: formNotes || undefined,
        });
      } else {
        const payload: AccountCreate = {
          name: formName,
          account_type: formType,
          institution: formInstitution || undefined,
          balance: parseFloat(formBalance) || 0,
          currency: formCurrency,
          notes: formNotes || undefined,
        };
        await createAccount(payload);
      }
      setDialogOpen(false);
      resetForm();
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save account');
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete account');
    }
  };

  const summaryCards = useMemo(() => {
    if (!overview) return [];
    return [
      {
        title: 'Net Worth',
        amount: currency(overview.net_worth),
        trend: overview.net_worth >= 0 ? 'up' : 'down',
        icon: Wallet,
        description: `${overview.account_count} account(s)`,
      },
      {
        title: 'Total Assets',
        amount: currency(overview.total_assets),
        trend: 'up',
        icon: TrendingUp,
        description: 'Active accounts',
      },
      {
        title: 'Total Liabilities',
        amount: currency(overview.total_liabilities),
        trend: 'down',
        icon: TrendingDown,
        description: 'Credit cards & loans',
      },
      {
        title: 'Monthly Net',
        amount: currency(overview.aggregate.monthly_net),
        trend: overview.aggregate.monthly_net >= 0 ? 'up' : 'down',
        icon: DollarSign,
        description: `Income: ${currency(overview.aggregate.monthly_income)}`,
      },
    ] as const;
  }, [overview]);

  const recentTx = overview?.recent_transactions ?? [];

  // Group accounts by type
  const groupedAccounts = useMemo(() => {
    const groups: Record<string, FinancialAccount[]> = {};
    for (const acct of accounts) {
      const key = acct.account_type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(acct);
    }
    return groups;
  }, [accounts]);

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Financial Accounts</h1>
            <p className="page-subtitle">
              Multi-account overview for {overview?.period?.month || month}.
            </p>
          </div>
          <div className="flex gap-3">
            <label className="sr-only" htmlFor="accounts-month">
              Month
            </label>
            <input
              id="accounts-month"
              aria-label="Accounts month"
              type="month"
              className="input h-9 w-[160px]"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
            <Button variant="outline" size="sm" onClick={() => void loadData()}>
              <RefreshCw className="w-4 h-4" />
              Refresh
            </Button>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="financial" size="sm" onClick={openCreateDialog}>
                  <Plus className="w-4 h-4" />
                  Add Account
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>
                    {editingAccount ? 'Edit Account' : 'Add Financial Account'}
                  </DialogTitle>
                  <DialogDescription>
                    {editingAccount
                      ? 'Update account details.'
                      : 'Link a new bank or financial account.'}
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid gap-2">
                    <Label htmlFor="acc-name">Account Name</Label>
                    <Input
                      id="acc-name"
                      placeholder="e.g. HDFC Savings"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="grid gap-2">
                      <Label htmlFor="acc-type">Type</Label>
                      <Select
                        value={formType}
                        onValueChange={(v) => setFormType(v as AccountType)}
                      >
                        <SelectTrigger id="acc-type">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(ACCOUNT_TYPE_LABELS).map(([k, label]) => (
                            <SelectItem key={k} value={k}>
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="acc-currency">Currency</Label>
                      <Input
                        id="acc-currency"
                        value={formCurrency}
                        onChange={(e) => setFormCurrency(e.target.value.toUpperCase())}
                        maxLength={10}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="grid gap-2">
                      <Label htmlFor="acc-institution">Institution</Label>
                      <Input
                        id="acc-institution"
                        placeholder="e.g. HDFC Bank"
                        value={formInstitution}
                        onChange={(e) => setFormInstitution(e.target.value)}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="acc-balance">Balance</Label>
                      <Input
                        id="acc-balance"
                        type="number"
                        step="0.01"
                        placeholder="0.00"
                        value={formBalance}
                        onChange={(e) => setFormBalance(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="acc-notes">Notes</Label>
                    <Input
                      id="acc-notes"
                      placeholder="Optional notes"
                      value={formNotes}
                      onChange={(e) => setFormNotes(e.target.value)}
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    variant="financial"
                    onClick={() => void handleSubmit()}
                    disabled={formSubmitting || !formName.trim()}
                  >
                    {formSubmitting
                      ? 'Saving...'
                      : editingAccount
                        ? 'Update Account'
                        : 'Create Account'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      {/* Summary Cards */}
      {!loading && overview && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
          {summaryCards.map((card, index) => (
            <FinancialCard
              key={index}
              variant="financial"
              className="group card-interactive fade-in-up"
            >
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                    {card.title}
                  </FinancialCardTitle>
                  <card.icon className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">{card.amount}</div>
                <div className="flex items-center text-sm">
                  {card.trend === 'up' ? (
                    <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                  ) : (
                    <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                  )}
                  <span className="text-muted-foreground">{card.description}</span>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      )}

      {loading && (
        <div className="text-center py-12 text-muted-foreground">Loading accounts...</div>
      )}

      {/* Accounts grouped by type */}
      {!loading && (
        <div className="grid lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            {Object.keys(groupedAccounts).length === 0 ? (
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardContent className="py-12 text-center">
                  <Building2 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">
                    No accounts yet. Add your first financial account to get started.
                  </p>
                  <Button
                    variant="financial"
                    size="sm"
                    className="mt-4"
                    onClick={openCreateDialog}
                  >
                    <Plus className="w-4 h-4" />
                    Add Account
                  </Button>
                </FinancialCardContent>
              </FinancialCard>
            ) : (
              Object.entries(groupedAccounts).map(([type, accts]) => {
                const Icon = ACCOUNT_TYPE_ICONS[type as AccountType] || Wallet;
                const label = ACCOUNT_TYPE_LABELS[type as AccountType] || type;
                return (
                  <FinancialCard key={type} variant="financial" className="fade-in-up">
                    <FinancialCardHeader>
                      <div className="flex items-center gap-2">
                        <Icon className="w-5 h-5 text-primary" />
                        <FinancialCardTitle className="section-title">
                          {label} Accounts
                        </FinancialCardTitle>
                      </div>
                      <FinancialCardDescription>
                        {accts.length} account{accts.length !== 1 ? 's' : ''}
                      </FinancialCardDescription>
                    </FinancialCardHeader>
                    <FinancialCardContent>
                      <div className="space-y-3">
                        {accts.map((acct) => {
                          // Find per-account stats from overview
                          const stats = overview?.accounts.find((a) => a.id === acct.id);
                          return (
                            <div
                              key={acct.id}
                              className="interactive-row flex items-center justify-between p-3 rounded-lg"
                            >
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium text-foreground">
                                    {acct.name}
                                  </span>
                                  {acct.institution && (
                                    <span className="text-xs text-muted-foreground">
                                      {acct.institution}
                                    </span>
                                  )}
                                </div>
                                {stats && (
                                  <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
                                    <span>
                                      Income: {currency(stats.monthly_income, acct.currency)}
                                    </span>
                                    <span>
                                      Expenses: {currency(stats.monthly_expenses, acct.currency)}
                                    </span>
                                    <span>{stats.transaction_count} txn(s)</span>
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="font-semibold text-foreground">
                                  {currency(acct.balance, acct.currency)}
                                </span>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8"
                                  onClick={() => openEditDialog(acct)}
                                >
                                  <Edit3 className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-destructive"
                                  onClick={() => void handleDelete(acct.id)}
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </FinancialCardContent>
                  </FinancialCard>
                );
              })
            )}
          </div>

          {/* Right sidebar: recent transactions */}
          <div>
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">
                  Recent Transactions
                </FinancialCardTitle>
                <FinancialCardDescription>
                  Across all accounts
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                {recentTx.length === 0 ? (
                  <div className="text-sm text-muted-foreground">
                    No transactions yet.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {recentTx.map((tx) => {
                      const isIncome = tx.type === 'INCOME';
                      const acctName = accounts.find(
                        (a) => a.id === tx.account_id,
                      )?.name;
                      return (
                        <div
                          key={tx.id}
                          className="interactive-row flex items-center justify-between"
                        >
                          <div className="flex items-center space-x-3">
                            <div
                              className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                                isIncome
                                  ? 'bg-success-light text-success'
                                  : 'bg-destructive-light text-destructive'
                              }`}
                            >
                              {isIncome ? (
                                <ArrowUpRight className="w-4 h-4" />
                              ) : (
                                <ArrowDownRight className="w-4 h-4" />
                              )}
                            </div>
                            <div>
                              <div className="font-medium text-foreground text-sm">
                                {tx.description}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {new Date(tx.date).toLocaleDateString()}
                                {acctName && ` - ${acctName}`}
                              </div>
                            </div>
                          </div>
                          <div
                            className={`text-sm font-semibold ${isIncome ? 'text-success' : 'text-foreground'}`}
                          >
                            {isIncome ? '+' : '-'}
                            {currency(Math.abs(tx.amount), tx.currency)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </FinancialCardContent>
              <FinancialCardFooter>
                <div className="w-full text-center text-xs text-muted-foreground">
                  Showing last {recentTx.length} transactions
                </div>
              </FinancialCardFooter>
            </FinancialCard>
          </div>
        </div>
      )}
    </div>
  );
}

export default Accounts;
