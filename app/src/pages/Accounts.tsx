import { useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { CreditCard, Building2, TrendingUp, TrendingDown, Plus, Wallet, PiggyBank, BarChart3, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

type AccountType = 'checking' | 'savings' | 'credit' | 'investment';

interface Account {
  id: number;
  name: string;
  institution: string;
  type: AccountType;
  balance: number;
  currency: string;
  lastUpdated: string;
  recentTransactions: Transaction[];
  change: number; // % change vs last month
}

interface Transaction {
  id: number;
  description: string;
  amount: number;
  date: string;
  type: 'debit' | 'credit';
}

const TYPE_CONFIG: Record<AccountType, { icon: React.ElementType; color: string; label: string }> = {
  checking: { icon: Wallet, color: 'text-primary', label: 'Checking' },
  savings: { icon: PiggyBank, color: 'text-success', label: 'Savings' },
  credit: { icon: CreditCard, color: 'text-destructive', label: 'Credit Card' },
  investment: { icon: BarChart3, color: 'text-accent', label: 'Investment' },
};

const initialAccounts: Account[] = [
  {
    id: 1,
    name: 'Chase Checking',
    institution: 'Chase Bank',
    type: 'checking',
    balance: 4823.50,
    currency: 'USD',
    lastUpdated: '2026-04-02',
    change: +2.3,
    recentTransactions: [
      { id: 1, description: 'Direct Deposit', amount: 3200, date: '2026-04-01', type: 'credit' },
      { id: 2, description: 'Amazon', amount: -89.99, date: '2026-03-31', type: 'debit' },
      { id: 3, description: 'Whole Foods', amount: -67.40, date: '2026-03-30', type: 'debit' },
    ],
  },
  {
    id: 2,
    name: 'Marcus High-Yield',
    institution: 'Goldman Sachs',
    type: 'savings',
    balance: 12450.00,
    currency: 'USD',
    lastUpdated: '2026-04-02',
    change: +4.8,
    recentTransactions: [
      { id: 4, description: 'Interest', amount: 47.23, date: '2026-04-01', type: 'credit' },
      { id: 5, description: 'Transfer In', amount: 500, date: '2026-03-28', type: 'credit' },
    ],
  },
  {
    id: 3,
    name: 'Chase Sapphire',
    institution: 'Chase Bank',
    type: 'credit',
    balance: -1240.88,
    currency: 'USD',
    lastUpdated: '2026-04-02',
    change: -8.2,
    recentTransactions: [
      { id: 6, description: 'Delta Airlines', amount: -342.00, date: '2026-03-30', type: 'debit' },
      { id: 7, description: 'Uber Eats', amount: -34.50, date: '2026-03-29', type: 'debit' },
      { id: 8, description: 'Payment', amount: 1000, date: '2026-03-28', type: 'credit' },
    ],
  },
  {
    id: 4,
    name: 'Fidelity Brokerage',
    institution: 'Fidelity',
    type: 'investment',
    balance: 28750.00,
    currency: 'USD',
    lastUpdated: '2026-04-02',
    change: +12.4,
    recentTransactions: [
      { id: 9, description: 'AAPL Dividend', amount: 23.50, date: '2026-04-01', type: 'credit' },
      { id: 10, description: 'VTI Purchase', amount: -500, date: '2026-03-29', type: 'debit' },
    ],
  },
];

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Math.abs(amount));
}

export function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>(initialAccounts);
  const [open, setOpen] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const { toast } = useToast();

  const [newAccount, setNewAccount] = useState({
    name: '', institution: '', type: 'checking' as AccountType, balance: '',
  });

  // Net worth = assets - liabilities
  const assets = accounts
    .filter(a => a.type !== 'credit' || a.balance > 0)
    .reduce((sum, a) => sum + Math.max(a.balance, 0), 0);
  const liabilities = accounts
    .filter(a => a.balance < 0)
    .reduce((sum, a) => sum + Math.abs(a.balance), 0);
  const netWorth = assets - liabilities;

  const byType: Record<AccountType, Account[]> = {
    checking: accounts.filter(a => a.type === 'checking'),
    savings: accounts.filter(a => a.type === 'savings'),
    credit: accounts.filter(a => a.type === 'credit'),
    investment: accounts.filter(a => a.type === 'investment'),
  };

  function handleAddAccount() {
    if (!newAccount.name || !newAccount.institution || !newAccount.balance) return;
    const account: Account = {
      id: Date.now(),
      name: newAccount.name,
      institution: newAccount.institution,
      type: newAccount.type,
      balance: parseFloat(newAccount.balance),
      currency: 'USD',
      lastUpdated: new Date().toISOString().split('T')[0],
      change: 0,
      recentTransactions: [],
    };
    setAccounts(prev => [...prev, account]);
    setNewAccount({ name: '', institution: '', type: 'checking', balance: '' });
    setOpen(false);
    toast({ title: 'Account added', description: `${account.name} has been linked.` });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Accounts</h1>
          <p className="text-muted-foreground">Your complete financial overview across all accounts</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2"><Plus className="h-4 w-4" />Add Account</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Link New Account</DialogTitle></DialogHeader>
            <div className="space-y-4 pt-2">
              <div>
                <Label>Account Name</Label>
                <Input placeholder="e.g. Chase Checking" value={newAccount.name}
                  onChange={e => setNewAccount(p => ({ ...p, name: e.target.value }))} />
              </div>
              <div>
                <Label>Institution</Label>
                <Input placeholder="e.g. Chase Bank" value={newAccount.institution}
                  onChange={e => setNewAccount(p => ({ ...p, institution: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Account Type</Label>
                  <select className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={newAccount.type}
                    onChange={e => setNewAccount(p => ({ ...p, type: e.target.value as AccountType }))}>
                    <option value="checking">Checking</option>
                    <option value="savings">Savings</option>
                    <option value="credit">Credit Card</option>
                    <option value="investment">Investment</option>
                  </select>
                </div>
                <div>
                  <Label>Current Balance ($)</Label>
                  <Input type="number" placeholder="0.00" value={newAccount.balance}
                    onChange={e => setNewAccount(p => ({ ...p, balance: e.target.value }))} />
                </div>
              </div>
              <Button className="w-full" onClick={handleAddAccount}>Link Account</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Net Worth Summary */}
      <div className="grid gap-4 md:grid-cols-3">
        <FinancialCard className="md:col-span-1 border-primary/30 bg-primary/5">
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="flex items-center gap-2">
              <Building2 className="h-4 w-4" /> Net Worth
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-3xl font-bold">{formatCurrency(netWorth)}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {formatCurrency(assets)} assets — {formatCurrency(liabilities)} liabilities
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-success" /> Total Assets
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold text-success">{formatCurrency(assets)}</div>
            <p className="text-xs text-muted-foreground">
              {accounts.filter(a => a.balance > 0).length} accounts
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-destructive" /> Total Liabilities
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold text-destructive">{formatCurrency(liabilities)}</div>
            <p className="text-xs text-muted-foreground">
              {accounts.filter(a => a.balance < 0).length} credit accounts
            </p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Accounts by type */}
      {(Object.keys(byType) as AccountType[]).map(type => {
        const accts = byType[type];
        if (accts.length === 0) return null;
        const { icon: Icon, color, label } = TYPE_CONFIG[type];
        const typeTotal = accts.reduce((sum, a) => sum + a.balance, 0);

        return (
          <div key={type}>
            <div className="flex items-center gap-2 mb-3">
              <Icon className={`h-4 w-4 ${color}`} />
              <h2 className="font-semibold">{label}</h2>
              <Badge variant="outline" className="ml-auto">{formatCurrency(typeTotal)}</Badge>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {accts.map(account => (
                <FinancialCard key={account.id}
                  className="cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => setSelectedAccount(selectedAccount?.id === account.id ? null : account)}>
                  <FinancialCardHeader className="pb-2">
                    <div className="flex justify-between items-start">
                      <div>
                        <FinancialCardTitle className="text-base">{account.name}</FinancialCardTitle>
                        <FinancialCardDescription>{account.institution}</FinancialCardDescription>
                      </div>
                      <div className="text-right">
                        <div className={`text-lg font-bold ${account.balance < 0 ? 'text-destructive' : ''}`}>
                          {account.balance < 0 ? '-' : ''}{formatCurrency(account.balance)}
                        </div>
                        <div className={`text-xs flex items-center justify-end gap-0.5 ${account.change >= 0 ? 'text-success' : 'text-destructive'}`}>
                          {account.change >= 0
                            ? <ArrowUpRight className="h-3 w-3" />
                            : <ArrowDownRight className="h-3 w-3" />}
                          {Math.abs(account.change)}% vs last month
                        </div>
                      </div>
                    </div>
                  </FinancialCardHeader>

                  {/* Recent transactions (expanded) */}
                  {selectedAccount?.id === account.id && account.recentTransactions.length > 0 && (
                    <FinancialCardContent className="pt-0">
                      <div className="border-t pt-3 space-y-2">
                        <p className="text-xs font-medium text-muted-foreground">Recent Transactions</p>
                        {account.recentTransactions.map(tx => (
                          <div key={tx.id} className="flex justify-between text-sm">
                            <span className="text-muted-foreground truncate max-w-[60%]">{tx.description}</span>
                            <span className={tx.amount > 0 ? 'text-success' : 'text-destructive'}>
                              {tx.amount > 0 ? '+' : ''}{formatCurrency(tx.amount)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </FinancialCardContent>
                  )}
                </FinancialCard>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default Accounts;
