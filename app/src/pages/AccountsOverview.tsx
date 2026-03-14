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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
  CreditCard,
  Banknote,
  TrendingUp,
  PiggyBank,
  MoreHorizontal,
  Plus,
  Trash2,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
} from 'lucide-react';
import { formatMoney } from '@/lib/currency';
import {
  type AccountCreate,
  type AccountOverview,
  type AccountType,
  type FinancialAccount,
  createAccount,
  deleteAccount,
  getAccountsOverview,
} from '@/api/accounts';
import { useToast } from '@/components/ui/use-toast';

const ACCOUNT_TYPE_META: Record<AccountType, { label: string; icon: typeof Wallet; accent: string }> = {
  BANK: { label: 'Bank', icon: Banknote, accent: 'text-blue-600' },
  CREDIT: { label: 'Credit Card', icon: CreditCard, accent: 'text-red-500' },
  CASH: { label: 'Cash', icon: Wallet, accent: 'text-green-600' },
  INVESTMENT: { label: 'Investment', icon: TrendingUp, accent: 'text-purple-600' },
  WALLET: { label: 'Wallet', icon: PiggyBank, accent: 'text-amber-600' },
  OTHER: { label: 'Other', icon: MoreHorizontal, accent: 'text-gray-500' },
};

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

export default function AccountsOverview() {
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const { toast } = useToast();

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAccountsOverview();
      setOverview(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const handleCreate = async (form: AccountCreate) => {
    try {
      await createAccount(form);
      toast({ title: 'Account created', description: `${form.name} added successfully.` });
      setDialogOpen(false);
      void loadOverview();
    } catch (e: unknown) {
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : 'Failed to create account',
        variant: 'destructive',
      });
    }
  };

  const handleDelete = async (acct: FinancialAccount) => {
    if (!window.confirm(`Deactivate "${acct.name}"?`)) return;
    try {
      await deleteAccount(acct.id);
      toast({ title: 'Account deactivated', description: `${acct.name} removed.` });
      void loadOverview();
    } catch (e: unknown) {
      toast({
        title: 'Error',
        description: e instanceof Error ? e.message : 'Failed to delete',
        variant: 'destructive',
      });
    }
  };

  if (loading) {
    return (
      <div className="container-financial py-8 space-y-6 animate-pulse">
        <div className="h-8 bg-muted rounded w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 bg-muted rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container-financial py-8">
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="text-destructive">Error</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p>{error}</p>
            <Button className="mt-4" onClick={() => void loadOverview()}>
              <RefreshCw className="mr-2 h-4 w-4" /> Retry
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      </div>
    );
  }

  const data = overview!;

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Accounts Overview</h1>
          <p className="text-sm text-muted-foreground">
            {data.total_accounts} account{data.total_accounts !== 1 ? 's' : ''} connected
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button variant="hero" size="sm">
              <Plus className="mr-2 h-4 w-4" /> Add Account
            </Button>
          </DialogTrigger>
          <CreateAccountDialog onSubmit={handleCreate} />
        </Dialog>
      </div>

      {/* Summary strip */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          title="Net Worth"
          value={currency(data.net_worth)}
          trend={data.net_worth >= 0 ? 'up' : 'down'}
          description="Assets minus liabilities"
          Icon={Wallet}
        />
        <SummaryCard
          title="Total Assets"
          value={currency(data.total_assets)}
          trend="up"
          description="All non-credit accounts"
          Icon={ArrowUpRight}
        />
        <SummaryCard
          title="Total Liabilities"
          value={currency(data.total_liabilities)}
          trend="down"
          description="Credit card balances"
          Icon={ArrowDownRight}
        />
        <SummaryCard
          title="Accounts"
          value={String(data.total_accounts)}
          description="Active accounts"
          Icon={CreditCard}
        />
      </div>

      {/* Account cards */}
      {data.accounts.length > 0 ? (
        <div>
          <h2 className="text-lg font-semibold mb-4">Your Accounts</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.accounts.map((acct) => {
              const meta = ACCOUNT_TYPE_META[acct.account_type as AccountType] || ACCOUNT_TYPE_META.OTHER;
              const Icon = meta.icon;
              return (
                <FinancialCard key={acct.id}>
                  <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <div className="flex items-center gap-2">
                      <div
                        className="flex h-8 w-8 items-center justify-center rounded-lg"
                        style={{ backgroundColor: `${acct.color}20` }}
                      >
                        <Icon className="h-4 w-4" style={{ color: acct.color }} />
                      </div>
                      <div>
                        <FinancialCardTitle className="text-sm font-semibold">{acct.name}</FinancialCardTitle>
                        <FinancialCardDescription className="text-xs">
                          {meta.label}
                          {acct.institution ? ` · ${acct.institution}` : ''}
                          {acct.last_four ? ` ··${acct.last_four}` : ''}
                        </FinancialCardDescription>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                      onClick={() => void handleDelete(acct)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </FinancialCardHeader>
                  <FinancialCardContent>
                    <p className="text-2xl font-bold">{currency(acct.balance, acct.currency)}</p>
                  </FinancialCardContent>
                  <FinancialCardFooter>
                    <span className="text-xs text-muted-foreground">{acct.currency}</span>
                  </FinancialCardFooter>
                </FinancialCard>
              );
            })}
          </div>
        </div>
      ) : (
        <FinancialCard>
          <FinancialCardContent className="flex flex-col items-center justify-center py-12">
            <Wallet className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground text-sm">No accounts yet. Add your first financial account above.</p>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Recent transactions */}
      {data.recent_transactions.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Recent Transactions</h2>
          <FinancialCard>
            <FinancialCardContent className="divide-y">
              {data.recent_transactions.map((tx) => (
                <div key={tx.id} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                  <div>
                    <p className="text-sm font-medium">{tx.notes || 'Expense'}</p>
                    <p className="text-xs text-muted-foreground">{tx.date}</p>
                  </div>
                  <p className="text-sm font-semibold text-destructive">-{currency(tx.amount, tx.currency)}</p>
                </div>
              ))}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Breakdown by type */}
      {Object.keys(data.by_type).length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">By Account Type</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(data.by_type).map(([type, info]) => {
              const meta = ACCOUNT_TYPE_META[type as AccountType] || ACCOUNT_TYPE_META.OTHER;
              const Icon = meta.icon;
              return (
                <FinancialCard key={type}>
                  <FinancialCardHeader className="flex flex-row items-center gap-2 space-y-0 pb-1">
                    <Icon className={`h-4 w-4 ${meta.accent}`} />
                    <FinancialCardTitle className="text-sm">{meta.label}</FinancialCardTitle>
                  </FinancialCardHeader>
                  <FinancialCardContent>
                    <p className="text-xl font-bold">{currency(info.total_balance)}</p>
                    <p className="text-xs text-muted-foreground">{info.count} account{info.count !== 1 ? 's' : ''}</p>
                  </FinancialCardContent>
                </FinancialCard>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────
function SummaryCard({
  title,
  value,
  description,
  trend,
  Icon,
}: {
  title: string;
  value: string;
  description: string;
  trend?: 'up' | 'down';
  Icon: typeof Wallet;
}) {
  return (
    <FinancialCard>
      <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <FinancialCardTitle className="text-xs font-medium text-muted-foreground">{title}</FinancialCardTitle>
        <Icon
          className={`h-4 w-4 ${
            trend === 'up' ? 'text-emerald-600' : trend === 'down' ? 'text-red-500' : 'text-muted-foreground'
          }`}
        />
      </FinancialCardHeader>
      <FinancialCardContent>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </FinancialCardContent>
    </FinancialCard>
  );
}

function CreateAccountDialog({ onSubmit }: { onSubmit: (data: AccountCreate) => void }) {
  const [name, setName] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('BANK');
  const [currency, setCurrency] = useState('USD');
  const [balance, setBalance] = useState('0');
  const [institution, setInstitution] = useState('');
  const [color, setColor] = useState('#3B82F6');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name: name.trim(),
      account_type: accountType,
      currency: currency.toUpperCase(),
      balance: parseFloat(balance) || 0,
      institution: institution.trim() || undefined,
      color,
    });
  };

  return (
    <DialogContent className="sm:max-w-[425px]">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <DialogTitle>Add Account</DialogTitle>
          <DialogDescription>Connect a new financial account to track.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="name">Account Name *</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Main Checking" required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Type</Label>
              <Select value={accountType} onValueChange={(v) => setAccountType(v as AccountType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(ACCOUNT_TYPE_META).map(([key, meta]) => (
                    <SelectItem key={key} value={key}>{meta.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="currency">Currency</Label>
              <Input id="currency" value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="USD" maxLength={10} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="balance">Balance</Label>
              <Input id="balance" type="number" step="0.01" value={balance} onChange={(e) => setBalance(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="color">Color</Label>
              <Input id="color" type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-10" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="institution">Institution (optional)</Label>
            <Input id="institution" value={institution} onChange={(e) => setInstitution(e.target.value)} placeholder="e.g. Chase, Bank of America" />
          </div>
        </div>
        <DialogFooter>
          <Button type="submit" disabled={!name.trim()}>
            Create Account
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
