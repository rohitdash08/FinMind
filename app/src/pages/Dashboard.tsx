import { useEffect, useMemo, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  ArrowDownRight,
  ArrowUpRight,
  CreditCard,
  TrendingDown,
  TrendingUp,
  Wallet,
  AlertTriangle,
  Calendar,
  Plus,
} from 'lucide-react';
import { getDashboardSummary, type DashboardSummary } from '@/api/dashboard';
import { useNavigate } from 'react-router-dom';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

export function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getDashboardSummary(month, selectedAccountIds);
        setData(res);
      } catch (error: unknown) {
        setError(error instanceof Error ? error.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    })();
  }, [month, selectedAccountIds]);

  const summary = useMemo(() => {
    if (!data) {
      return {
        net_flow: 0,
        monthly_income: 0,
        monthly_expenses: 0,
        upcoming_bills_total: 0,
        upcoming_bills_count: 0,
        total_balance: 0,
        account_count: 0,
        selected_account_count: 0,
      };
    }
    return data.summary;
  }, [data]);

  const summaryCards = [
    {
      title: 'Total Balance',
      amount: currency(summary.total_balance || 0),
      change: `${summary.selected_account_count || summary.account_count || 0} account(s)`,
      trend: 'up',
      icon: Wallet,
      description: selectedAccountIds.length > 0 ? 'Selected accounts' : 'All accounts',
    },
    {
      title: 'Net Flow',
      amount: currency(summary.net_flow),
      change: summary.net_flow >= 0 ? 'Positive' : 'Negative',
      trend: summary.net_flow >= 0 ? 'up' : 'down',
      icon: Wallet,
      description: 'Current month',
    },
    {
      title: 'Monthly Income',
      amount: currency(summary.monthly_income),
      change: '+',
      trend: 'up',
      icon: TrendingUp,
      description: 'Current month',
    },
    {
      title: 'Monthly Expenses',
      amount: currency(summary.monthly_expenses),
      change: '-',
      trend: 'down',
      icon: TrendingDown,
      description: 'Current month',
    },
    {
      title: 'Upcoming Bills',
      amount: currency(summary.upcoming_bills_total),
      change: `${summary.upcoming_bills_count} bill(s)`,
      trend: 'up',
      icon: CreditCard,
      description: 'Due soon',
    },
  ] as const;

  const accounts = data?.accounts ?? [];
  const accountBreakdown = data?.account_breakdown ?? [];
  const transactions = data?.recent_transactions ?? [];
  const upcomingBills = data?.upcoming_bills ?? [];
  const categoryBreakdown = data?.category_breakdown ?? [];

  function toggleAccount(accountId: number) {
    setSelectedAccountIds((current) => (
      current.includes(accountId)
        ? current.filter((id) => id !== accountId)
        : [...current, accountId].sort((a, b) => a - b)
    ));
  }

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Financial Dashboard</h1>
            <p className="page-subtitle">Live overview for {data?.period?.month || 'current period'}.</p>
          </div>
          <div className="flex gap-3">
            <label className="sr-only" htmlFor="dashboard-month">Dashboard month</label>
            <input
              id="dashboard-month"
              aria-label="Dashboard month"
              type="month"
              className="input h-9 w-[160px]"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
            <Button variant="outline" size="sm" onClick={() => setMonth(new Date().toISOString().slice(0, 7))}>
              <Calendar className="w-4 h-4" />
              This Month
            </Button>
            <Button variant="financial" size="sm" onClick={() => navigate('/expenses')}>
              <Plus className="w-4 h-4" />
              Add Transaction
            </Button>
          </div>
        </div>
      </div>

      {error && (
        <div className="error mb-6">{error}. Showing empty fallback state.</div>
      )}

      {data?.errors && data.errors.length > 0 && (
        <div className="card mb-6 text-sm text-warning">
          Some widgets are temporarily unavailable: {data.errors.join(', ')}
        </div>
      )}

      <FinancialCard variant="financial" className="mb-6 fade-in-up">
        <FinancialCardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <FinancialCardTitle className="section-title">Account Overview</FinancialCardTitle>
              <FinancialCardDescription>Filter the dashboard by one or more financial accounts.</FinancialCardDescription>
            </div>
            {selectedAccountIds.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => setSelectedAccountIds([])}>
                Show All
              </Button>
            )}
          </div>
        </FinancialCardHeader>
        <FinancialCardContent>
          {accounts.length === 0 ? (
            <div className="text-sm text-muted-foreground">No accounts yet. Add accounts from the Accounts page to see balances here.</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {accounts.map((account) => {
                const selected = selectedAccountIds.includes(account.id);
                return (
                  <button
                    key={account.id}
                    type="button"
                    onClick={() => toggleAccount(account.id)}
                    className={`rounded-xl border p-3 text-left transition hover:border-primary ${selected ? 'border-primary bg-primary/5' : 'border-border bg-background'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground">{account.name}</span>
                      <span className="text-xs text-muted-foreground">{account.account_type.replace('_', ' ')}</span>
                    </div>
                    <div className="mt-2 text-lg font-semibold">{currency(account.balance, account.currency)}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Net this month {currency(account.monthly_net_flow, account.currency)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5 mb-8">
        {summaryCards.map((card, index) => (
          <FinancialCard key={index} variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">{card.title}</FinancialCardTitle>
                <card.icon className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">{loading ? '...' : card.amount}</div>
              <div className="flex items-center text-sm">
                {card.trend === 'up' ? (
                  <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                ) : (
                  <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                )}
                <span className={card.trend === 'up' ? 'text-success font-medium mr-2' : 'text-destructive font-medium mr-2'}>{card.change}</span>
                <span className="text-muted-foreground">{card.description}</span>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="section-title">Recent Transactions</FinancialCardTitle>
                <Button variant="ghost" size="sm" onClick={() => navigate('/expenses')}>View All</Button>
              </div>
              <FinancialCardDescription>Your latest financial activity</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {transactions.length === 0 ? (
                <div className="text-sm text-muted-foreground">No transactions yet.</div>
              ) : (
                <div className="space-y-3">
                  {transactions.map((transaction) => {
                    const isIncome = transaction.type === 'INCOME';
                    return (
                      <div key={transaction.id} className="interactive-row flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                            isIncome ? 'bg-success-light text-success' : 'bg-destructive-light text-destructive'
                          }`}>
                            {isIncome ? <ArrowUpRight className="w-5 h-5" /> : <ArrowDownRight className="w-5 h-5" />}
                          </div>
                          <div>
                            <div className="font-medium text-foreground">{transaction.description}</div>
                            <div className="text-sm text-muted-foreground">
                              {new Date(transaction.date).toLocaleDateString()}
                              {transaction.account_name ? ` · ${transaction.account_name}` : ''}
                            </div>
                          </div>
                        </div>
                        <div className={`font-semibold ${isIncome ? 'text-success' : 'text-foreground'}`}>
                          {isIncome ? '+' : '-'}
                          {currency(Math.abs(transaction.amount), transaction.currency)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>

        <div className="space-y-6">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="section-title">Upcoming Bills</FinancialCardTitle>
                <Button variant="ghost" size="sm" onClick={() => navigate('/bills')}>Manage</Button>
              </div>
              <FinancialCardDescription>Active bills due soon</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {upcomingBills.length === 0 ? (
                <div className="text-sm text-muted-foreground">No upcoming bills.</div>
              ) : (
                <div className="space-y-3">
                  {upcomingBills.map((bill) => (
                    <div key={bill.id} className="interactive-row flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-warning-light text-warning">
                          <AlertTriangle className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="font-medium text-foreground text-sm">{bill.name}</div>
                          <div className="text-xs text-muted-foreground">Due {new Date(bill.next_due_date).toLocaleDateString()}</div>
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-foreground">
                        {currency(bill.amount, bill.currency)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </FinancialCardContent>
            <FinancialCardFooter>
              <Button variant="financial" size="sm" className="w-full" onClick={() => navigate('/bills')}>
                <Plus className="w-4 h-4" />
                Add New Bill
              </Button>
            </FinancialCardFooter>
          </FinancialCard>

          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Account Breakdown</FinancialCardTitle>
              <FinancialCardDescription>Balance and monthly movement by account</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {accountBreakdown.length === 0 ? (
                <div className="text-sm text-muted-foreground">No account data yet.</div>
              ) : (
                <div className="space-y-3">
                  {accountBreakdown.slice(0, 6).map((account) => (
                    <div key={account.id} className="interactive-row space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-foreground">{account.name}</span>
                        <span className="text-foreground">{currency(account.balance, account.currency)}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Income {currency(account.monthly_income, account.currency)} · Expenses {currency(account.monthly_expenses, account.currency)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Category Breakdown</FinancialCardTitle>
              <FinancialCardDescription>Expense mix for {data?.period?.month || month}</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {categoryBreakdown.length === 0 ? (
                <div className="text-sm text-muted-foreground">No category data for this month.</div>
              ) : (
                <div className="space-y-3">
                  {categoryBreakdown.slice(0, 6).map((row) => (
                    <div key={`${row.category_id ?? 'uncat'}-${row.category_name}`} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-foreground">{row.category_name}</span>
                        <span className="text-muted-foreground">{currency(row.amount)} ({row.share_pct.toFixed(0)}%)</span>
                      </div>
                      <div className="chart-track h-2">
                        <div className="chart-fill-primary h-2" style={{ width: `${Math.max(2, Math.min(100, row.share_pct))}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      </div>
    </div>
  );
}
