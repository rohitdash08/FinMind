import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { me, updateMe } from '@/api/auth';
import { createAccount, listAccounts, type FinancialAccount } from '@/api/accounts';
import { setCurrency } from '@/lib/auth';
import { formatMoney } from '@/lib/currency';

const SUPPORTED_CURRENCIES = [
  { code: 'INR', label: 'Indian Rupee (INR)' },
  { code: 'USD', label: 'US Dollar (USD)' },
  { code: 'EUR', label: 'Euro (EUR)' },
  { code: 'GBP', label: 'British Pound (GBP)' },
  { code: 'AED', label: 'UAE Dirham (AED)' },
  { code: 'SGD', label: 'Singapore Dollar (SGD)' },
  { code: 'AUD', label: 'Australian Dollar (AUD)' },
  { code: 'CAD', label: 'Canadian Dollar (CAD)' },
  { code: 'JPY', label: 'Japanese Yen (JPY)' },
];

export default function Account() {
  const { toast } = useToast();
  const [email, setEmail] = useState('');
  const [currency, setCurrencyState] = useState('INR');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [accountName, setAccountName] = useState('');
  const [accountType, setAccountType] = useState('CHECKING');
  const [openingBalance, setOpeningBalance] = useState('0');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await me();
        const accountData = await listAccounts();
        setEmail(data.email);
        setCurrencyState(data.preferred_currency || 'INR');
        setAccounts(accountData);
      } catch (error: unknown) {
        const message =
          error instanceof Error ? error.message : 'Failed to load account';
        toast({ title: 'Failed to load account', description: message });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [toast]);

  const onSave = async () => {
    setSaving(true);
    try {
      const updated = await updateMe({ preferred_currency: currency });
      setCurrency(updated.preferred_currency);
      toast({
        title: 'Account updated',
        description: `Default currency set to ${updated.preferred_currency}.`,
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to update account';
      toast({ title: 'Failed to update account', description: message });
    } finally {
      setSaving(false);
    }
  };

  const onCreateAccount = async () => {
    const name = accountName.trim();
    if (!name) {
      toast({ title: 'Account name required' });
      return;
    }
    setSaving(true);
    try {
      const account = await createAccount({
        name,
        account_type: accountType,
        currency,
        opening_balance: Number(openingBalance || 0),
      });
      setAccounts((items) => [...items, account].sort((a, b) => a.name.localeCompare(b.name)));
      setAccountName('');
      setOpeningBalance('0');
      toast({ title: 'Financial account added' });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to create account';
      toast({ title: 'Failed to create account', description: message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Account Settings</h1>
          <p className="page-subtitle">
            Manage your profile defaults. Currency stays fixed until you change
            it again.
          </p>
        </div>
      </div>

      <div className="card card-interactive space-y-5 fade-in-up">
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading account...</div>
        ) : (
          <>
            <div className="space-y-2">
              <Label>Email</Label>
              <div className="input bg-muted/30">{email}</div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="preferred_currency">Preferred Currency</Label>
              <select
                id="preferred_currency"
                className="input"
                value={currency}
                onChange={(e) => setCurrencyState(e.target.value)}
              >
                {SUPPORTED_CURRENCIES.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end">
              <Button
                variant="financial"
                onClick={onSave}
                disabled={saving || loading}
              >
                {saving ? 'Saving...' : 'Save Preferences'}
              </Button>
            </div>
          </>
        )}
      </div>

      <div className="card card-interactive space-y-5 fade-in-up">
        <div>
          <h2 className="section-title">Financial Accounts</h2>
          <p className="text-sm text-muted-foreground">
            Add accounts to compare income, spending, and projected balances on the dashboard.
          </p>
        </div>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading accounts...</div>
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-4">
              <input
                aria-label="Account name"
                className="input"
                placeholder="Account name"
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
              />
              <select
                aria-label="Account type"
                className="input"
                value={accountType}
                onChange={(e) => setAccountType(e.target.value)}
              >
                <option value="CHECKING">Checking</option>
                <option value="SAVINGS">Savings</option>
                <option value="CREDIT">Credit</option>
                <option value="CASH">Cash</option>
                <option value="INVESTMENT">Investment</option>
                <option value="OTHER">Other</option>
              </select>
              <input
                aria-label="Opening balance"
                className="input"
                inputMode="decimal"
                placeholder="Opening balance"
                value={openingBalance}
                onChange={(e) => setOpeningBalance(e.target.value)}
              />
              <Button variant="financial" onClick={onCreateAccount} disabled={saving}>
                Add Account
              </Button>
            </div>
            {accounts.length === 0 ? (
              <div className="text-sm text-muted-foreground">No financial accounts yet.</div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {accounts.map((account) => (
                  <div key={account.id} className="interactive-row flex items-center justify-between">
                    <div>
                      <div className="font-medium text-foreground">{account.name}</div>
                      <div className="text-xs text-muted-foreground">{account.account_type}</div>
                    </div>
                    <div className="text-sm font-semibold text-foreground">
                      {formatMoney(account.opening_balance, account.currency)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
