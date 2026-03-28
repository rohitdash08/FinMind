import { useState, useMemo } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardFooter,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Plus,
  CreditCard,
  Wallet,
  Building2,
  TrendingUp,
  Landmark,
  Banknote,
  Trash2,
  Edit,
  Star,
  ArrowUpRight,
  ArrowDownRight,
  PiggyBank,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import type { FinancialAccount, AccountType, CreateAccountRequest } from '@/api/accounts';

// --- Constants --------------------------------------------------------------

const ACCOUNT_TYPES: { value: AccountType; label: string; icon: typeof Wallet }[] = [
  { value: 'checking', label: 'Checking', icon: Landmark },
  { value: 'savings', label: 'Savings', icon: PiggyBank },
  { value: 'credit_card', label: 'Credit Card', icon: CreditCard },
  { value: 'investment', label: 'Investment', icon: TrendingUp },
  { value: 'cash', label: 'Cash', icon: Banknote },
  { value: 'loan', label: 'Loan', icon: Building2 },
  { value: 'other', label: 'Other', icon: Wallet },
];

const ACCOUNT_COLORS = [
  '#6366f1', '#22c55e', '#f59e0b', '#ec4899', '#06b6d4', '#8b5cf6', '#f97316', '#ef4444',
];

const INSTITUTIONS = [
  'Chase', 'Bank of America', 'Wells Fargo', 'Citi', 'Capital One',
  'Fidelity', 'Vanguard', 'Schwab', 'Robinhood', 'PayPal', 'Venmo', 'Cash App', 'Other',
];

// --- Mock Data --------------------------------------------------------------

const mockAccounts: FinancialAccount[] = [
  {
    id: '1', name: 'Primary Checking', type: 'checking', balance: 4520.50,
    currency: 'USD', institution: 'Chase', color: '#6366f1', isPrimary: true,
    lastSyncedAt: '2026-03-28T02:00:00Z', createdAt: '2025-01-01', updatedAt: '2026-03-28',
  },
  {
    id: '2', name: 'Emergency Savings', type: 'savings', balance: 12800.00,
    currency: 'USD', institution: 'Chase', color: '#22c55e', isPrimary: false,
    lastSyncedAt: '2026-03-28T02:00:00Z', createdAt: '2025-01-01', updatedAt: '2026-03-28',
  },
  {
    id: '3', name: 'Rewards Card', type: 'credit_card', balance: -1245.30,
    currency: 'USD', institution: 'Capital One', color: '#f59e0b', isPrimary: false,
    lastSyncedAt: '2026-03-27T18:00:00Z', createdAt: '2025-03-15', updatedAt: '2026-03-27',
  },
  {
    id: '4', name: 'Brokerage', type: 'investment', balance: 28450.00,
    currency: 'USD', institution: 'Fidelity', color: '#06b6d4', isPrimary: false,
    lastSyncedAt: '2026-03-27T20:00:00Z', createdAt: '2025-06-01', updatedAt: '2026-03-27',
  },
  {
    id: '5', name: 'Cash Wallet', type: 'cash', balance: 320.00,
    currency: 'USD', institution: 'Cash', color: '#22c55e', isPrimary: false,
    lastSyncedAt: '2026-03-28T10:00:00Z', createdAt: '2025-09-01', updatedAt: '2026-03-28',
  },
];

// --- Helpers ----------------------------------------------------------------

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(amount);
}

function getAccountIcon(type: AccountType) {
  return ACCOUNT_TYPES.find((t) => t.value === type)?.icon || Wallet;
}

function getAccountTypeLabel(type: AccountType) {
  return ACCOUNT_TYPES.find((t) => t.value === type)?.label || 'Other';
}

// --- Component --------------------------------------------------------------

export function Accounts() {
  const [accounts, setAccounts] = useState<FinancialAccount[]>(mockAccounts);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [formData, setFormData] = useState<CreateAccountRequest>({
    name: '', type: 'checking', balance: 0, institution: 'Other', color: ACCOUNT_COLORS[0],
  });
  const { toast } = useToast();

  const summary = useMemo(() => {
    const totalAssets = accounts.filter((a) => a.balance > 0).reduce((s, a) => s + a.balance, 0);
    const totalLiabilities = Math.abs(accounts.filter((a) => a.balance < 0).reduce((s, a) => s + a.balance, 0));
    const totalBalance = totalAssets - totalLiabilities;
    const byType: Record<string, { count: number; total: number }> = {};
    accounts.forEach((a) => {
      if (!byType[a.type]) byType[a.type] = { count: 0, total: 0 };
      byType[a.type].count++;
      byType[a.type].total += a.balance;
    });
    return { totalBalance, totalAssets, totalLiabilities, accountCount: accounts.length, byType };
  }, [accounts]);

  const handleCreate = () => {
    if (!formData.name || !formData.institution) {
      toast({ title: 'Validation Error', description: 'Please fill in all required fields.', variant: 'destructive' });
      return;
    }
    const newAccount: FinancialAccount = {
      id: Date.now().toString(),
      ...formData,
      currency: 'USD',
      isPrimary: accounts.length === 0,
      lastSyncedAt: new Date().toISOString(),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setAccounts((prev) => [...prev, newAccount]);
    setIsCreateOpen(false);
    setFormData({ name: '', type: 'checking', balance: 0, institution: 'Other', color: ACCOUNT_COLORS[0] });
    toast({ title: 'Account Added', description: `"${newAccount.name}" has been added.` });
  };

  const handleDelete = (account: FinancialAccount) => {
    setAccounts((prev) => prev.filter((a) => a.id !== account.id));
    toast({ title: 'Account Removed', description: `"${account.name}" has been removed.` });
  };

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Accounts</h1>
          <p className="text-muted-foreground">View all your financial accounts in one place.</p>
        </div>
        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2"><Plus className="h-4 w-4" />Add Account</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Add Financial Account</DialogTitle>
              <DialogDescription>Link a new account to track your finances.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="acc-name">Account Name</Label>
                <Input id="acc-name" placeholder="e.g., Chase Checking" value={formData.name}
                  onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="acc-type">Type</Label>
                  <Select value={formData.type} onValueChange={(v) => setFormData((p) => ({ ...p, type: v as AccountType }))}>
                    <SelectTrigger id="acc-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {ACCOUNT_TYPES.map((t) => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="acc-balance">Balance ($)</Label>
                  <Input id="acc-balance" type="number" step="0.01" placeholder="0.00"
                    value={formData.balance || ''} onChange={(e) => setFormData((p) => ({ ...p, balance: parseFloat(e.target.value) || 0 }))} />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="acc-institution">Institution</Label>
                <Select value={formData.institution} onValueChange={(v) => setFormData((p) => ({ ...p, institution: v }))}>
                  <SelectTrigger id="acc-institution"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {INSTITUTIONS.map((inst) => (
                      <SelectItem key={inst} value={inst}>{inst}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateOpen(false)}>Cancel</Button>
              <Button onClick={handleCreate}>Add Account</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Net Worth</FinancialCardDescription>
            <FinancialCardTitle className={`text-2xl ${summary.totalBalance >= 0 ? 'text-success' : 'text-destructive'}`}>
              {formatCurrency(summary.totalBalance)}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground">{summary.accountCount} accounts</p>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Total Assets</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-success">
              {formatCurrency(summary.totalAssets)}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <ArrowUpRight className="h-3 w-3" /> Positive balances
            </p>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Total Liabilities</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-destructive">
              {formatCurrency(summary.totalLiabilities)}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <ArrowDownRight className="h-3 w-3" /> Credit & loans
            </p>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>By Type</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-1">
              {Object.entries(summary.byType).map(([type, data]) => (
                <div key={type} className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{getAccountTypeLabel(type as AccountType)}</span>
                  <span className="font-medium">{formatCurrency(data.total)}</span>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Account Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {accounts.map((account) => {
          const Icon = getAccountIcon(account.type);
          const isLiability = account.balance < 0;
          return (
            <FinancialCard key={account.id} className="relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-1" style={{ backgroundColor: account.color }} />
              <FinancialCardHeader className="pt-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${account.color}20` }}>
                      <Icon className="h-5 w-5" style={{ color: account.color }} />
                    </div>
                    <div>
                      <FinancialCardTitle className="text-base flex items-center gap-1">
                        {account.name}
                        {account.isPrimary && <Star className="h-3 w-3 text-warning fill-warning" />}
                      </FinancialCardTitle>
                      <FinancialCardDescription>{account.institution}</FinancialCardDescription>
                    </div>
                  </div>
                  <Badge variant="outline">{getAccountTypeLabel(account.type)}</Badge>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="flex items-baseline justify-between">
                  <span className={`text-2xl font-bold ${isLiability ? 'text-destructive' : 'text-foreground'}`}>
                    {formatCurrency(account.balance)}
                  </span>
                  <span className="text-xs text-muted-foreground">{account.currency}</span>
                </div>
              </FinancialCardContent>
              <FinancialCardFooter className="gap-2">
                <Button size="sm" variant="outline" className="flex-1 gap-1">
                  <Edit className="h-4 w-4" /> Edit
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="sm" variant="outline" className="gap-1">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Remove Account</AlertDialogTitle>
                      <AlertDialogDescription>
                        Are you sure you want to remove "{account.name}"? This will not delete any transactions.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={() => handleDelete(account)}>Remove</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </FinancialCardFooter>
            </FinancialCard>
          );
        })}
      </div>
    </div>
  );
}
