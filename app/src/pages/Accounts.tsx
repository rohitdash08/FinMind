import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Wallet,
  Plus,
  Trash2,
  Building2,
  CreditCard,
  PiggyBank,
  Banknote,
  TrendingUp,
  MoreHorizontal,
  Receipt,
  CalendarClock,
} from 'lucide-react';
import {
  getAccountsOverview,
  createAccount,
  updateAccount,
  deleteAccount,
  type FinancialAccount,
  type AccountCreate,
  type AccountsOverview,
} from '@/api/accounts';

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  CHECKING: 'Checking',
  SAVINGS: 'Savings',
  CREDIT_CARD: 'Credit Card',
  CASH: 'Cash',
  INVESTMENT: 'Investment',
  OTHER: 'Other',
};

const ACCOUNT_TYPE_ICONS: Record<string, typeof Wallet> = {
  CHECKING: Wallet,
  SAVINGS: PiggyBank,
  CREDIT_CARD: CreditCard,
  CASH: Banknote,
  INVESTMENT: TrendingUp,
  OTHER: MoreHorizontal,
};

export default function Accounts() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);

  const { data: overview, isLoading } = useQuery<AccountsOverview>({
    queryKey: ['accounts-overview'],
    queryFn: getAccountsOverview,
  });

  const createMutation = useMutation({
    mutationFn: (payload: AccountCreate) => createAccount(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts-overview'] });
      setCreateOpen(false);
      toast({ title: 'Account created', description: 'Your financial account has been added.' });
    },
    onError: (err: Error) => {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts-overview'] });
      toast({ title: 'Account deleted' });
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => updateAccount(id, { active: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts-overview'] });
      toast({ title: 'Account deactivated' });
    },
  });

  const handleCreate = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const payload: AccountCreate = {
      name: form.get('name') as string,
      account_type: (form.get('account_type') as string) || 'CHECKING',
      balance: Number(form.get('balance') || 0),
      currency: (form.get('currency') as string) || undefined,
      institution: (form.get('institution') as string) || undefined,
    };
    createMutation.mutate(payload);
  };

  const accounts = overview?.accounts ?? [];
  const totalBalance = overview?.total_balance ?? 0;
  const recentExpenses = overview?.recent_expenses ?? [];
  const upcomingBills = overview?.upcoming_bills ?? [];

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="h-6 w-6 text-primary" />
            Financial Accounts
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            View all your accounts in one place
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button variant="hero">
              <Plus className="h-4 w-4 mr-2" />
              Add Account
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Financial Account</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <Label htmlFor="name">Account Name</Label>
                <Input id="name" name="name" placeholder="e.g. Main Checking" required />
              </div>
              <div>
                <Label htmlFor="account_type">Account Type</Label>
                <select
                  id="account_type"
                  name="account_type"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  defaultValue="CHECKING"
                >
                  {Object.entries(ACCOUNT_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="balance">Current Balance</Label>
                  <Input
                    id="balance"
                    name="balance"
                    type="number"
                    step="0.01"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <Label htmlFor="currency">Currency</Label>
                  <Input id="currency" name="currency" placeholder="USD" />
                </div>
              </div>
              <div>
                <Label htmlFor="institution">Institution (optional)</Label>
                <Input id="institution" name="institution" placeholder="e.g. Chase Bank" />
              </div>
              <Button type="submit" className="w-full" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Adding...' : 'Add Account'}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <FinancialCard variant="premium">
          <FinancialCardHeader>
            <FinancialCardDescription>Total Balance</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              ${totalBalance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardDescription>Active Accounts</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {overview?.account_count ?? 0}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardDescription>Upcoming Bills</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {upcomingBills.length}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground text-center py-12">Loading accounts...</p>
      ) : accounts.length === 0 ? (
        <FinancialCard variant="financial" className="text-center py-12">
          <FinancialCardContent>
            <Wallet className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
              No financial accounts yet. Add your first account to get started!
            </p>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="space-y-8">
          {/* Accounts Grid */}
          <div>
            <h2 className="text-lg font-semibold mb-4">Your Accounts</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {accounts.map((account) => (
                <AccountCard
                  key={account.id}
                  account={account}
                  onDeactivate={() => deactivateMutation.mutate(account.id)}
                  onDelete={() => deleteMutation.mutate(account.id)}
                />
              ))}
            </div>
          </div>

          {/* Recent Activity */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Recent Expenses */}
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Receipt className="h-4 w-4" />
                  Recent Expenses
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {recentExpenses.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No recent expenses</p>
                ) : (
                  <div className="space-y-3">
                    {recentExpenses.map((expense) => (
                      <div key={expense.id} className="flex justify-between items-center text-sm">
                        <div>
                          <p className="font-medium">{expense.description || 'Expense'}</p>
                          <p className="text-xs text-muted-foreground">{expense.date}</p>
                        </div>
                        <span className="font-semibold text-destructive">
                          -{expense.currency} {expense.amount.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>

            {/* Upcoming Bills */}
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <CalendarClock className="h-4 w-4" />
                  Upcoming Bills
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {upcomingBills.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No upcoming bills</p>
                ) : (
                  <div className="space-y-3">
                    {upcomingBills.map((bill) => (
                      <div key={bill.id} className="flex justify-between items-center text-sm">
                        <div>
                          <p className="font-medium">{bill.name}</p>
                          <p className="text-xs text-muted-foreground">Due: {bill.next_due_date}</p>
                        </div>
                        <span className="font-semibold">
                          {bill.currency} {bill.amount.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>
          </div>
        </div>
      )}
    </div>
  );
}

function AccountCard({
  account,
  onDeactivate,
  onDelete,
}: {
  account: FinancialAccount;
  onDeactivate: () => void;
  onDelete: () => void;
}) {
  const Icon = ACCOUNT_TYPE_ICONS[account.account_type] || Wallet;

  return (
    <FinancialCard variant="financial">
      <FinancialCardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <div>
              <FinancialCardTitle className="text-base">{account.name}</FinancialCardTitle>
              <FinancialCardDescription>
                {ACCOUNT_TYPE_LABELS[account.account_type]}
              </FinancialCardDescription>
            </div>
          </div>
        </div>
      </FinancialCardHeader>
      <FinancialCardContent className="space-y-3">
        <div>
          <p className="text-2xl font-bold">
            {account.currency} {account.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </p>
        </div>
        {account.institution && (
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <Building2 className="h-3 w-3" />
            {account.institution}
          </p>
        )}
        <div className="flex gap-2 pt-2">
          <Button size="sm" variant="outline" onClick={onDeactivate}>
            Deactivate
          </Button>
          <Button size="sm" variant="ghost" className="text-destructive ml-auto" onClick={onDelete}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}
