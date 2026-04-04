import { useEffect, useState } from 'react';
import { getAccounts, createAccount, type FinancialAccount } from '@/api/accounts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function Accounts() {
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [type, setType] = useState('checking');
  const [balance, setBalance] = useState('');

  const load = () => { getAccounts().then(setAccounts).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);

  const assets = accounts.filter((a) => a.account_type !== 'credit').reduce((s, a) => s + a.balance, 0);
  const liabilities = accounts.filter((a) => a.account_type === 'credit').reduce((s, a) => s + a.balance, 0);
  const netWorth = assets - liabilities;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name) return;
    await createAccount({ name, account_type: type, balance: parseFloat(balance || '0') });
    setName(''); setBalance('');
    load();
  };

  if (loading) return <div className="p-6 text-center text-muted-foreground">Loading…</div>;

  return (
    <div className="container-financial py-8 space-y-6">
      <h1 className="text-2xl font-bold">Accounts Overview</h1>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Total Assets</CardTitle></CardHeader><CardContent><p className="text-2xl font-bold text-green-600">${assets.toFixed(2)}</p></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Total Liabilities</CardTitle></CardHeader><CardContent><p className="text-2xl font-bold text-destructive">${liabilities.toFixed(2)}</p></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Net Worth</CardTitle></CardHeader><CardContent><p className="text-2xl font-bold">${netWorth.toFixed(2)}</p></CardContent></Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Add Account</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="flex flex-wrap gap-3">
            <Input placeholder="Account name" value={name} onChange={(e) => setName(e.target.value)} className="w-48" required />
            <select value={type} onChange={(e) => setType(e.target.value)} className="rounded-md border px-3 py-2 text-sm" aria-label="Account type">
              <option value="checking">Checking</option>
              <option value="savings">Savings</option>
              <option value="credit">Credit</option>
            </select>
            <Input type="number" placeholder="Balance" value={balance} onChange={(e) => setBalance(e.target.value)} className="w-36" step="0.01" />
            <Button type="submit">Add</Button>
          </form>
        </CardContent>
      </Card>

      {accounts.length === 0 && <p className="text-center text-muted-foreground">No accounts yet.</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {accounts.map((a) => (
          <Card key={a.id}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{a.name}</CardTitle>
              <span className="text-xs uppercase text-muted-foreground">{a.account_type}</span>
            </CardHeader>
            <CardContent>
              <p className={`text-xl font-bold ${a.account_type === 'credit' ? 'text-destructive' : ''}`}>${a.balance.toFixed(2)}</p>
              {a.last_transaction && <p className="text-xs text-muted-foreground mt-1">Last: {a.last_transaction}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
