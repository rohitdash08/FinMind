import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import {
  archiveAccount,
  createAccount,
  listAccounts,
  updateAccount,
  type AccountType,
  type FinancialAccount,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';

const accountTypes: AccountType[] = [
  'CASH',
  'CHECKING',
  'SAVINGS',
  'CREDIT_CARD',
  'INVESTMENT',
  'LOAN',
  'WALLET',
  'OTHER',
];

export default function Accounts() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<FinancialAccount | null>(null);
  const [name, setName] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('CHECKING');
  const [institution, setInstitution] = useState('');
  const [lastFour, setLastFour] = useState('');
  const [currency, setCurrency] = useState('INR');
  const [openingBalance, setOpeningBalance] = useState('0');
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAccounts(await listAccounts());
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to load accounts';
      setError(message);
      toast({ title: 'Failed to load accounts', description: message });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const totals = useMemo(() => {
    const balance = accounts.reduce((sum, account) => sum + Number(account.balance || 0), 0);
    return { balance };
  }, [accounts]);

  function resetForm() {
    setEditing(null);
    setName('');
    setAccountType('CHECKING');
    setInstitution('');
    setLastFour('');
    setCurrency('INR');
    setOpeningBalance('0');
    setError(null);
  }

  function startEdit(account: FinancialAccount) {
    setEditing(account);
    setName(account.name);
    setAccountType(account.account_type);
    setInstitution(account.institution || '');
    setLastFour(account.last_four || '');
    setCurrency(account.currency || 'INR');
    setOpeningBalance(String(account.opening_balance ?? 0));
  }

  async function saveAccount() {
    if (!name.trim()) {
      setError('Account name is required');
      return;
    }
    if (Number.isNaN(Number(openingBalance))) {
      setError('Opening balance must be a number');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: name.trim(),
        account_type: accountType,
        institution: institution.trim() || null,
        last_four: lastFour.trim() || null,
        currency: currency.trim() || 'INR',
        opening_balance: Number(openingBalance || 0),
      };
      if (editing) {
        const updated = await updateAccount(editing.id, payload);
        setAccounts((prev) => prev.map((account) => (account.id === updated.id ? updated : account)));
        toast({ title: 'Account updated' });
      } else {
        const created = await createAccount(payload);
        setAccounts((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
        toast({ title: 'Account created' });
      }
      resetForm();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to save account';
      setError(message);
      toast({ title: 'Failed to save account', description: message });
    } finally {
      setSaving(false);
    }
  }

  async function archive(id: number) {
    setSaving(true);
    try {
      await archiveAccount(id);
      setAccounts((prev) => prev.filter((account) => account.id !== id));
      if (editing?.id === id) resetForm();
      toast({ title: 'Account archived' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to archive account';
      setError(message);
      toast({ title: 'Failed to archive account', description: message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap space-y-5">
      <div className="page-header">
        <div className="relative flex items-center justify-between gap-4">
          <div>
            <h2 className="page-title text-2xl md:text-3xl">Financial Accounts</h2>
            <p className="page-subtitle">Track cash, bank, card, wallet, and savings balances in one place.</p>
          </div>
          <div className="card px-4 py-3 text-right">
            <div className="text-xs text-muted-foreground">Total balance</div>
            <div className="text-xl font-semibold">{formatMoney(totals.balance, accounts[0]?.currency)}</div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <div className="card card-interactive p-4 space-y-3 fade-in-up">
          <h3 className="text-base font-semibold">{editing ? 'Edit account' : 'Add account'}</h3>
          <div>
            <Label htmlFor="account-name">Name</Label>
            <Input id="account-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Main checking" />
          </div>
          <div>
            <Label htmlFor="account-type">Type</Label>
            <select id="account-type" className="input" value={accountType} onChange={(e) => setAccountType(e.target.value as AccountType)}>
              {accountTypes.map((type) => (
                <option key={type} value={type}>{type.replace('_', ' ')}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="institution">Institution</Label>
            <Input id="institution" value={institution} onChange={(e) => setInstitution(e.target.value)} placeholder="Bank or provider" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="last-four">Last 4</Label>
              <Input id="last-four" value={lastFour} onChange={(e) => setLastFour(e.target.value)} maxLength={4} />
            </div>
            <div>
              <Label htmlFor="currency">Currency</Label>
              <Input id="currency" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={10} />
            </div>
          </div>
          <div>
            <Label htmlFor="opening-balance">Opening balance</Label>
            <Input id="opening-balance" type="number" step="0.01" value={openingBalance} onChange={(e) => setOpeningBalance(e.target.value)} />
          </div>
          {error && <div className="error">{error}</div>}
          <div className="flex gap-2">
            <Button onClick={saveAccount} disabled={saving}>{editing ? 'Save account' : 'Create account'}</Button>
            {editing && <Button variant="outline" onClick={resetForm} disabled={saving}>Cancel</Button>}
          </div>
        </div>

        <div className="card fade-in-up">
          {loading ? (
            <div>Loading accounts...</div>
          ) : accounts.length === 0 ? (
            <div className="text-sm text-muted-foreground">No accounts yet. Add one to unlock the multi-account dashboard.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="py-2">Account</th>
                    <th className="py-2">Type</th>
                    <th className="py-2">Opening</th>
                    <th className="py-2">Balance</th>
                    <th className="py-2">Activity</th>
                    <th className="py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((account) => (
                    <tr key={account.id} className="border-t transition-colors hover:bg-muted/30">
                      <td className="py-3">
                        <div className="font-medium">{account.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {[account.institution, account.last_four ? `•••• ${account.last_four}` : null].filter(Boolean).join(' · ') || 'Manual account'}
                        </div>
                      </td>
                      <td className="py-3">{account.account_type.replace('_', ' ')}</td>
                      <td className="py-3">{formatMoney(account.opening_balance, account.currency)}</td>
                      <td className="py-3 font-semibold">{formatMoney(account.balance, account.currency)}</td>
                      <td className="py-3 text-xs text-muted-foreground">
                        Income {formatMoney(account.income_total, account.currency)} · Expenses {formatMoney(account.expense_total, account.currency)}
                      </td>
                      <td className="py-3">
                        <div className="flex justify-end gap-2">
                          <Button variant="outline" onClick={() => startEdit(account)} disabled={saving}>Edit</Button>
                          <Button variant="outline" onClick={() => archive(account.id)} disabled={saving}>Archive</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
