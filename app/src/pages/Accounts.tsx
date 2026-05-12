import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardFooter, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Wallet, Plus, Landmark, CreditCard, Banknote, PiggyBank, TrendingUp, ArrowUpRight, ArrowDownRight, DollarSign } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { createAccount, deleteAccount, getAccountSummary, getAccountsOverview, type AccountSummary, type AccountOverview } from '@/api/accounts';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  checking: 'Checking',
  savings: 'Savings',
  credit_card: 'Credit Card',
  cash: 'Cash',
  investment: 'Investment',
};

function AccountTypeIcon({ type, className }: { type: string; className?: string }) {
  const cn = className || 'w-6 h-6';
  switch (type) {
    case 'checking':
      return <Landmark className={cn} />;
    case 'savings':
      return <PiggyBank className={cn} />;
    case 'credit_card':
      return <CreditCard className={cn} />;
    case 'cash':
      return <Banknote className={cn} />;
    case 'investment':
      return <TrendingUp className={cn} />;
    default:
      return <Wallet className={cn} />;
  }
}

export default function Accounts() {
  const { toast } = useToast();
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<AccountSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [accountType, setAccountType] = useState('checking');
  const [currency, setCurrency] = useState('INR');
  const [initialBalance, setInitialBalance] = useState('');
  const [saving, setSaving] = useState(false);

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAccountsOverview();
      setOverview(data);
    } catch (error: unknown) {
      toast({ title: 'Failed to load accounts', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onSelectAccount(accountId: number) {
    setSummaryLoading(true);
    try {
      const data = await getAccountSummary(accountId);
      setSelectedAccount(data);
    } catch (error: unknown) {
      toast({ title: 'Failed to load account details', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setSummaryLoading(false);
    }
  }

  async function onCreate() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await createAccount({
        name: name.trim(),
        account_type: accountType,
        currency: currency.toUpperCase(),
        initial_balance: initialBalance ? Number(initialBalance) : 0,
      });
      await refresh();
      setOpen(false);
      setName('');
      setAccountType('checking');
      setCurrency('INR');
      setInitialBalance('');
      toast({ title: 'Account created' });
    } catch (error: unknown) {
      toast({ title: 'Failed to create account', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    try {
      await deleteAccount(id);
      toast({ title: 'Account deleted' });
      if (selectedAccount?.account.id === id) {
        setSelectedAccount(null);
      }
      await refresh();
    } catch (error: unknown) {
      toast({ title: 'Failed to delete account', description: getErrorMessage(error, 'Please try again.') });
    }
  }

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Accounts</h1>
            <p className="page-subtitle">
              Manage your financial accounts and track balances
            </p>
          </div>
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
                <DialogDescription>Add a financial account to track.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm mb-1">Name</label>
                  <input className="input w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="Main Checking" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm mb-1">Account Type</label>
                    <select className="input w-full" value={accountType} onChange={(e) => setAccountType(e.target.value)}>
                      <option value="checking">Checking</option>
                      <option value="savings">Savings</option>
                      <option value="credit_card">Credit Card</option>
                      <option value="cash">Cash</option>
                      <option value="investment">Investment</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm mb-1">Currency</label>
                    <input className="input w-full" value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="INR" maxLength={3} />
                  </div>
                </div>
                <div>
                  <label className="block text-sm mb-1">Initial Balance</label>
                  <input className="input w-full" type="number" min="0" step="0.01" value={initialBalance} onChange={(e) => setInitialBalance(e.target.value)} placeholder="0.00" />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
                <Button onClick={onCreate} disabled={saving || !name.trim()}>Create</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {loading ? (
        <div>Loading...</div>
      ) : (
        <>
          {overview && (
            <div className="mb-8">
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                      Total Net Worth
                    </FinancialCardTitle>
                    <DollarSign className="w-5 h-5 text-muted-foreground" />
                  </div>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <div className="metric-value text-foreground mb-1">
                    {formatMoney(overview.total_net_worth)}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Across {overview.accounts.length} account{overview.accounts.length !== 1 ? 's' : ''}
                  </div>
                </FinancialCardContent>
              </FinancialCard>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-8">
            {overview?.accounts.map((item) => (
              <FinancialCard
                key={item.account.id}
                variant="financial"
                className="fade-in-up cursor-pointer hover:ring-2 hover:ring-primary/30 transition-all"
                onClick={() => onSelectAccount(item.account.id)}
              >
                <FinancialCardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                        <AccountTypeIcon type={item.account.account_type} className="w-5 h-5" />
                      </div>
                      <div>
                        <FinancialCardTitle className="text-sm font-medium">
                          {item.account.name}
                        </FinancialCardTitle>
                        <div className="text-xs text-muted-foreground">
                          {ACCOUNT_TYPE_LABELS[item.account.account_type] || item.account.account_type}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      {item.account.is_default && (
                        <Badge variant="secondary" className="text-xs">Default</Badge>
                      )}
                      <Badge variant="outline" className="text-xs">{item.account.currency}</Badge>
                    </div>
                  </div>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <div className="metric-value text-foreground mb-2">
                    {formatMoney(item.balance, item.account.currency)}
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center text-success">
                      <ArrowUpRight className="w-3 h-3 mr-1" />
                      {formatMoney(item.total_income, item.account.currency)}
                    </div>
                    <div className="flex items-center text-destructive">
                      <ArrowDownRight className="w-3 h-3 mr-1" />
                      {formatMoney(item.total_expenses, item.account.currency)}
                    </div>
                  </div>
                  {item.monthly_spend > 0 && (
                    <div className="text-xs text-muted-foreground mt-2">
                      This month: {formatMoney(item.monthly_spend, item.account.currency)} spent
                    </div>
                  )}
                </FinancialCardContent>
                <FinancialCardFooter className="flex justify-end pt-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(item.account.id);
                    }}
                  >
                    Delete
                  </Button>
                </FinancialCardFooter>
              </FinancialCard>
            ))}
          </div>

          {overview?.accounts.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              <Wallet className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium mb-1">No accounts yet</p>
              <p className="text-sm">Add your first financial account to get started.</p>
            </div>
          )}

          {summaryLoading && (
            <div className="card fade-in-up p-6">Loading account details...</div>
          )}

          {selectedAccount && !summaryLoading && (
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <AccountTypeIcon type={selectedAccount.account.account_type} className="w-6 h-6" />
                    <div>
                      <FinancialCardTitle className="section-title">{selectedAccount.account.name}</FinancialCardTitle>
                      <FinancialCardDescription>
                        Recent transactions
                      </FinancialCardDescription>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-semibold">{formatMoney(selectedAccount.balance, selectedAccount.account.currency)}</div>
                    <div className="text-xs text-muted-foreground">Current balance</div>
                  </div>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="text-center p-3 rounded-lg bg-muted/50">
                    <div className="text-xs text-muted-foreground mb-1">Income</div>
                    <div className="font-semibold text-success">{formatMoney(selectedAccount.total_income, selectedAccount.account.currency)}</div>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-muted/50">
                    <div className="text-xs text-muted-foreground mb-1">Expenses</div>
                    <div className="font-semibold text-destructive">{formatMoney(selectedAccount.total_expenses, selectedAccount.account.currency)}</div>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-muted/50">
                    <div className="text-xs text-muted-foreground mb-1">This Month</div>
                    <div className="font-semibold">{formatMoney(selectedAccount.monthly_spend, selectedAccount.account.currency)}</div>
                  </div>
                </div>

                {selectedAccount.recent_transactions.length === 0 ? (
                  <div className="text-sm text-muted-foreground text-center py-4">No transactions yet for this account.</div>
                ) : (
                  <div className="space-y-2">
                    {selectedAccount.recent_transactions.map((txn) => (
                      <div key={txn.id} className="interactive-row flex items-center justify-between border-b py-2">
                        <div>
                          <div className="font-medium text-sm">{txn.description}</div>
                          <div className="text-xs text-muted-foreground">
                            {new Date(txn.date).toLocaleDateString()}
                          </div>
                        </div>
                        <div className={`font-semibold text-sm ${txn.type === 'INCOME' ? 'text-success' : 'text-destructive'}`}>
                          {txn.type === 'INCOME' ? '+' : '-'}{formatMoney(txn.amount, txn.currency)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>
          )}
        </>
      )}
    </div>
  );
}
