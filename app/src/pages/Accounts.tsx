import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Wallet, Plus, Building2, PiggyBank, CreditCard, Banknote, TrendingUp, Trash2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { listAccounts, createAccount, deleteAccount, getOverview, type Account, type AccountOverview, type AccountType } from '@/api/accounts';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPE_ICONS: Record<AccountType, typeof Wallet> = {
  checking: Building2,
  savings: PiggyBank,
  credit: CreditCard,
  cash: Banknote,
  investment: TrendingUp,
};

const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  checking: 'Checking',
  savings: 'Savings',
  credit: 'Credit Card',
  cash: 'Cash',
  investment: 'Investment',
};

export default function Accounts() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newAccount, setNewAccount] = useState<{ name: string; account_type: AccountType; balance: string; currency: string }>({
    name: '', account_type: 'checking', balance: '0', currency: 'INR',
  });

  const loadData = useCallback(async () => {
    try {
      const [accs, ov] = await Promise.all([listAccounts(), getOverview()]);
      setAccounts(accs);
      setOverview(ov);
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'Failed to load accounts', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    try {
      await createAccount({
        name: newAccount.name,
        account_type: newAccount.account_type,
        balance: parseFloat(newAccount.balance) || 0,
        currency: newAccount.currency,
      });
      toast({ title: 'Account created' });
      setDialogOpen(false);
      setNewAccount({ name: '', account_type: 'checking', balance: '0', currency: 'INR' });
      loadData();
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'Failed to create account', variant: 'destructive' });
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id);
      toast({ title: 'Account deactivated' });
      loadData();
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'Failed to deactivate', variant: 'destructive' });
    }
  };

  if (loading) return <div className="flex justify-center p-8">Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Accounts</h1>
          <p className="text-muted-foreground">Manage your financial accounts</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button><Plus className="mr-2 h-4 w-4" /> Add Account</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Account</DialogTitle>
              <DialogDescription>Add a new financial account to track.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <input className="w-full rounded-md border px-3 py-2" placeholder="Account name" value={newAccount.name} onChange={e => setNewAccount(p => ({ ...p, name: e.target.value }))} />
              <select className="w-full rounded-md border px-3 py-2" value={newAccount.account_type} onChange={e => setNewAccount(p => ({ ...p, account_type: e.target.value as AccountType }))}>
                {Object.entries(ACCOUNT_TYPE_LABELS).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
              </select>
              <input className="w-full rounded-md border px-3 py-2" type="number" placeholder="Balance" value={newAccount.balance} onChange={e => setNewAccount(p => ({ ...p, balance: e.target.value }))} />
              <input className="w-full rounded-md border px-3 py-2" placeholder="Currency (e.g. INR)" value={newAccount.currency} onChange={e => setNewAccount(p => ({ ...p, currency: e.target.value }))} />
            </div>
            <DialogFooter>
              <Button onClick={handleCreate} disabled={!newAccount.name}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Overview Cards */}
      {overview && (
        <div className="grid gap-4 md:grid-cols-3">
          <FinancialCard>
            <FinancialCardHeader><FinancialCardTitle>Total Balance</FinancialCardTitle></FinancialCardHeader>
            <FinancialCardContent><p className="text-2xl font-bold">{formatMoney(overview.total_balance)}</p></FinancialCardContent>
          </FinancialCard>
          <FinancialCard>
            <FinancialCardHeader><FinancialCardTitle>Net Worth</FinancialCardTitle></FinancialCardHeader>
            <FinancialCardContent><p className="text-2xl font-bold">{formatMoney(overview.net_worth)}</p></FinancialCardContent>
          </FinancialCard>
          <FinancialCard>
            <FinancialCardHeader><FinancialCardTitle>Active Accounts</FinancialCardTitle></FinancialCardHeader>
            <FinancialCardContent><p className="text-2xl font-bold">{overview.account_count}</p></FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Account List */}
      {accounts.length === 0 ? (
        <FinancialCard>
          <FinancialCardContent className="flex flex-col items-center justify-center py-12">
            <Wallet className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground">No accounts yet. Add your first account to get started.</p>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {accounts.map(account => {
            const Icon = ACCOUNT_TYPE_ICONS[account.account_type] || Wallet;
            return (
              <FinancialCard key={account.id}>
                <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
                  <div className="flex items-center gap-2">
                    <Icon className="h-5 w-5 text-muted-foreground" />
                    <FinancialCardTitle className="text-base">{account.name}</FinancialCardTitle>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{ACCOUNT_TYPE_LABELS[account.account_type]}</Badge>
                    <Button variant="ghost" size="icon" onClick={() => handleDelete(account.id)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <p className="text-2xl font-bold">{formatMoney(account.balance, account.currency)}</p>
                  <p className="text-xs text-muted-foreground mt-1">{account.currency}</p>
                </FinancialCardContent>
              </FinancialCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
