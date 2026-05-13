import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { Plus, Trash2, TrendingUp, Landmark, CreditCard, PiggyBank, Wallet } from 'lucide-react';
import {
  listAccounts,
  createAccount,
  deleteAccount,
  getConsolidatedView,
  type Account,
  type ConsolidatedView,
} from '@/api/accounts';

const ACCOUNT_TYPES = [
  { value: 'checking', label: 'Checking', icon: Wallet },
  { value: 'savings', label: 'Savings', icon: PiggyBank },
  { value: 'credit', label: 'Credit Card', icon: CreditCard },
  { value: 'investment', label: 'Investment', icon: TrendingUp },
  { value: 'cash', label: 'Cash', icon: Landmark },
];

function AccountTypeIcon({ type }: { type: string }) {
  const config = ACCOUNT_TYPES.find(t => t.value === type);
  if (!config) return <Wallet className="h-4 w-4" />;
  const Icon = config.icon;
  return <Icon className="h-4 w-4" />;
}

export default function AccountsPage() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [consolidated, setConsolidated] = useState<ConsolidatedView | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('checking');
  const [newBalance, setNewBalance] = useState('0');
  const [newCurrency, setNewCurrency] = useState('INR');

  const loadData = async () => {
    try {
      const [accts, cons] = await Promise.all([
        listAccounts(),
        getConsolidatedView(),
      ]);
      setAccounts(accts);
      setConsolidated(cons);
    } catch {
      toast({ title: 'Failed to load accounts', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await createAccount({
        name: newName,
        account_type: newType,
        balance: parseFloat(newBalance) || 0,
        currency: newCurrency,
      });
      setShowForm(false);
      setNewName('');
      setNewBalance('0');
      toast({ title: 'Account created' });
      loadData();
    } catch {
      toast({ title: 'Failed to create account', variant: 'destructive' });
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id);
      toast({ title: 'Account removed' });
      loadData();
    } catch {
      toast({ title: 'Failed to delete account', variant: 'destructive' });
    }
  };

  if (loading) return <div className="p-8 text-center">Loading accounts...</div>;

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Financial Accounts</h1>
        <Button onClick={() => setShowForm(!showForm)}>
          <Plus className="mr-2 h-4 w-4" /> Add Account
        </Button>
      </div>

      {/* Consolidated summary */}
      {consolidated && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-2xl">${consolidated.total_balance.toLocaleString()}</CardTitle><CardDescription>Total Balance</CardDescription></CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-2xl">{consolidated.account_count}</CardTitle><CardDescription>Accounts</CardDescription></CardHeader>
          </Card>
          {Object.entries(consolidated.by_type).slice(0, 2).map(([type, bal]) => (
            <Card key={type}>
              <CardHeader className="pb-2">
                <CardTitle className="text-xl">${bal.toLocaleString()}</CardTitle>
                <CardDescription className="capitalize">{type}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}

      {/* Add account form */}
      {showForm && (
        <Card>
          <CardHeader><CardTitle>New Account</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Account Name</Label>
              <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="e.g. Main Checking" />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={newType} onValueChange={setNewType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ACCOUNT_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Balance</Label>
              <Input type="number" value={newBalance} onChange={e => setNewBalance(e.target.value)} />
            </div>
            <Button onClick={handleCreate}>Create</Button>
          </CardContent>
        </Card>
      )}

      {/* Accounts list */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {accounts.map(a => (
          <Card key={a.id}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div className="flex items-center gap-2">
                <AccountTypeIcon type={a.account_type} />
                <CardTitle className="text-lg">{a.name}</CardTitle>
              </div>
              <Button variant="ghost" size="icon" onClick={() => handleDelete(a.id)}>
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">${a.balance.toLocaleString()}</p>
              <p className="text-sm text-muted-foreground capitalize">{a.account_type} · {a.currency}</p>
            </CardContent>
          </Card>
        ))}
        {accounts.length === 0 && !showForm && (
          <p className="text-muted-foreground col-span-full text-center py-8">
            No accounts yet. Add one to get started.
          </p>
        )}
      </div>
    </div>
  );
}
