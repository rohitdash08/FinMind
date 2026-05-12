import { useEffect, useMemo, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Building2, CreditCard, Plus, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import {
  createAccount,
  getAccountsOverview,
  type AccountType,
  type AccountsOverview,
} from '@/api/accounts';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPES: Array<{ value: AccountType; label: string }> = [
  { value: 'CHECKING', label: 'Checking' },
  { value: 'SAVINGS', label: 'Savings' },
  { value: 'CREDIT_CARD', label: 'Credit Card' },
  { value: 'INVESTMENT', label: 'Investment' },
  { value: 'LOAN', label: 'Loan' },
  { value: 'CASH', label: 'Cash' },
  { value: 'OTHER', label: 'Other' },
];

export function Accounts() {
  const { toast } = useToast();
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [data, setData] = useState<AccountsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    account_type: 'CHECKING' as AccountType,
    balance: '',
    currency: 'INR',
    institution: '',
  });

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await getAccountsOverview(month));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load accounts';
      setError(message);
      toast({ title: 'Failed to load accounts', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  const summaryCards = useMemo(() => {
    const summary = data?.summary ?? {
      account_count: 0,
      assets: 0,
      liabilities: 0,
      net_worth: 0,
    };
    return [
      { label: 'Net Worth', value: summary.net_worth, icon: Wallet },
      { label: 'Assets', value: summary.assets, icon: ArrowUpRight },
      { label: 'Liabilities', value: summary.liabilities, icon: ArrowDownRight },
      { label: 'Accounts', value: summary.account_count, icon: Building2, count: true },
    ];
  }, [data]);

  async function onCreate() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await createAccount({
        name: form.name.trim(),
        account_type: form.account_type,
        balance: Number(form.balance || 0),
        currency: form.currency.trim().toUpperCase() || 'INR',
        institution: form.institution.trim() || undefined,
      });
      setForm({
        name: '',
        account_type: 'CHECKING',
        balance: '',
        currency: form.currency.trim().toUpperCase() || 'INR',
        institution: '',
      });
      toast({ title: 'Account created' });
      await load();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create account';
      toast({ title: 'Failed to create account', description: message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="page-title">Accounts</h1>
            <p className="page-subtitle">Unified balances and activity across financial accounts.</p>
          </div>
          <div>
            <Label htmlFor="accounts-month">Month</Label>
            <Input
              id="accounts-month"
              aria-label="accounts month"
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
            />
          </div>
        </div>
      </div>

      {error ? <div className="card text-red-600">{error}</div> : null}

      <div className="grid gap-4 md:grid-cols-4">
        {summaryCards.map((item) => (
          <FinancialCard key={item.label} variant="financial">
            <FinancialCardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm">{item.label}</FinancialCardTitle>
                <item.icon className="h-5 w-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              {loading ? '...' : item.count ? item.value : formatMoney(item.value)}
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <FinancialCardTitle>Add Account</FinancialCardTitle>
          <FinancialCardDescription>Track balances and connect future transactions to an account.</FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="grid gap-3 md:grid-cols-6">
            <div className="md:col-span-2">
              <Label htmlFor="account-name">Name</Label>
              <Input
                id="account-name"
                aria-label="account name"
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Main checking"
              />
            </div>
            <div>
              <Label htmlFor="account-type">Type</Label>
              <select
                id="account-type"
                aria-label="account type"
                className="input"
                value={form.account_type}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, account_type: event.target.value as AccountType }))
                }
              >
                {ACCOUNT_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="account-balance">Balance</Label>
              <Input
                id="account-balance"
                aria-label="account balance"
                type="number"
                value={form.balance}
                onChange={(event) => setForm((prev) => ({ ...prev, balance: event.target.value }))}
                placeholder="0.00"
              />
            </div>
            <div>
              <Label htmlFor="account-currency">Currency</Label>
              <Input
                id="account-currency"
                aria-label="account currency"
                value={form.currency}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, currency: event.target.value.toUpperCase() }))
                }
                maxLength={10}
              />
            </div>
            <div>
              <Label htmlFor="account-institution">Institution</Label>
              <Input
                id="account-institution"
                aria-label="account institution"
                value={form.institution}
                onChange={(event) => setForm((prev) => ({ ...prev, institution: event.target.value }))}
                placeholder="Bank name"
              />
            </div>
          </div>
          <Button className="mt-4" onClick={onCreate} disabled={saving || !form.name.trim()}>
            <Plus className="h-4 w-4" />
            {saving ? 'Creating...' : 'Create Account'}
          </Button>
        </FinancialCardContent>
      </FinancialCard>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Account Overview</FinancialCardTitle>
              <FinancialCardDescription>Balances with monthly income and expense activity.</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.accounts.length ? (
                <div className="space-y-3">
                  {data.accounts.map((account) => (
                    <div key={account.id} className="interactive-row flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
                          {account.account_type === 'CREDIT_CARD' ? (
                            <CreditCard className="h-5 w-5" />
                          ) : (
                            <Wallet className="h-5 w-5" />
                          )}
                        </div>
                        <div>
                          <div className="font-medium">{account.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {account.institution || account.account_type.replace('_', ' ')}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-semibold">{formatMoney(account.balance, account.currency)}</div>
                        <div className="text-xs text-muted-foreground">
                          {formatMoney(account.monthly_net_flow || 0, account.currency)} this month
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">No accounts yet.</div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>

        <div className="space-y-6">
          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Currency Groups</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.by_currency.length ? (
                <div className="space-y-3">
                  {data.by_currency.map((row) => (
                    <div key={row.currency} className="rounded-lg border p-3">
                      <div className="flex justify-between text-sm">
                        <span>{row.currency}</span>
                        <span>{formatMoney(row.net_worth, row.currency)}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Assets {formatMoney(row.assets, row.currency)} · Liabilities {formatMoney(row.liabilities, row.currency)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">No currency data.</div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Recent Account Activity</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.recent_transactions.length ? (
                <div className="space-y-3">
                  {data.recent_transactions.slice(0, 5).map((item) => (
                    <div key={item.id} className="rounded-lg border p-3 text-sm">
                      <div className="flex justify-between gap-3">
                        <span>{item.description}</span>
                        <span>{formatMoney(item.amount, item.currency)}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{item.account_name}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">No linked account activity.</div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      </div>
    </div>
  );
}
