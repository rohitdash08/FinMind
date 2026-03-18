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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  Building2,
  Banknote,
  MoreHorizontal,
} from 'lucide-react';
import { getDashboardSummary, type DashboardSummary } from '@/api/dashboard';
import {
  getAccountOverview,
  ACCOUNT_TYPE_LABELS,
  type AccountOverview,
  type AccountType,
} from '@/api/accounts';
import { useNavigate } from 'react-router-dom';
import { formatMoney } from '@/lib/currency';

const ACCOUNT_TYPE_ICONS: Record<AccountType, React.ElementType> = {
  CHECKING: Wallet,
  SAVINGS: Building2,
  CREDIT: CreditCard,
  INVESTMENT: TrendingUp,
  CASH: Banknote,
  OTHER: MoreHorizontal,
};

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

export function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));

  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getDashboardSummary(month);
        setData(res);
      } catch (error: unknown) {
        setError(error instanceof Error ? error.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    })();
  }, [month]);

  useEffect(() => {
    (async () => {
      setOverviewLoading(true);
      setOverviewError(null);
      try {
        const res = await getAccountOverview(month);
        setOverview(res);
      } catch (err: unknown) {
        setOverviewError(err instanceof Error ? err.message : 'Failed to load account overview');
      } finally {
        setOverviewLoading(false);
      }
    })();
  }, [month]);

  const summary = useMemo(() => {
    if (!data) {
      return {
        net_flow: 0,
        monthly_income: 0,
        monthly_expenses: 0,
        upcoming_bills_total: 0,
        upcoming_bills_count: 0,
      };
    }
    return data.summary;
  }, [data]);

  const summaryCards = [
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

  const transactions = data?.recent_transactions ?? [];
  const upcomingBills = data?.upcoming_bills ?? [];
  const categoryBreakdown = data?.category_breakdown ?? [];

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Financial Dashboard</h1>
            <p className="page-subtitle">Live overview for {data?.period?.month || 'current period'}.</p>
          </div>
          <div className="flex gap-3 flex-wrap">
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
            <Button variant="outline" size="sm" onClick={() => navigate('/accounts')}>
              <Building2 className="w-4 h-4" />
              Accounts
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

      <Tabs defaultValue="summary" className="space-y-6">
        <TabsList>
          <TabsTrigger value="summary">Monthly Summary</TabsTrigger>
          <TabsTrigger value="accounts">Accounts Overview</TabsTrigger>
        </TabsList>

        {/* ── Monthly Summary Tab ── */}
        <TabsContent value="summary" className="space-y-8">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
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
                                <div className="text-sm text-muted-foreground">{new Date(transaction.date).toLocaleDateString()}</div>
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
        </TabsContent>

        {/* ── Accounts Overview Tab ── */}
        <TabsContent value="accounts" className="space-y-8">
          {overviewError && (
            <div className="error mb-4">{overviewError}</div>
          )}

          {/* Net worth + type breakdown */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <FinancialCard variant="financial" className="group card-interactive fade-in-up lg:col-span-1">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Net Worth</FinancialCardTitle>
                  <Wallet className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className={`metric-value mb-1 ${(overview?.net_worth ?? 0) >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {overviewLoading ? '...' : currency(overview?.net_worth ?? 0)}
                </div>
                <div className="text-xs text-muted-foreground">Across all accounts</div>
              </FinancialCardContent>
            </FinancialCard>

            {(overview?.account_summary_by_type ?? []).slice(0, 3).map((t) => {
              const Icon = ACCOUNT_TYPE_ICONS[t.account_type] ?? Wallet;
              return (
                <FinancialCard key={t.account_type} variant="financial" className="group card-interactive fade-in-up">
                  <FinancialCardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                        {ACCOUNT_TYPE_LABELS[t.account_type]}
                      </FinancialCardTitle>
                      <Icon className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </FinancialCardHeader>
                  <FinancialCardContent>
                    <div className="metric-value text-foreground mb-1">
                      {overviewLoading ? '...' : currency(t.total_balance)}
                    </div>
                    <div className="text-xs text-muted-foreground">Total balance</div>
                  </FinancialCardContent>
                </FinancialCard>
              );
            })}
          </div>

          <div className="grid lg:grid-cols-3 gap-8">
            {/* Per-account balance cards */}
            <div className="lg:col-span-2 space-y-4">
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <div className="flex items-center justify-between">
                    <FinancialCardTitle className="section-title">Account Balances</FinancialCardTitle>
                    <Button variant="ghost" size="sm" onClick={() => navigate('/accounts')}>Manage</Button>
                  </div>
                  <FinancialCardDescription>
                    {overview?.accounts.length ?? 0} active account{(overview?.accounts.length ?? 0) !== 1 ? 's' : ''}
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {overviewLoading ? (
                    <div className="text-sm text-muted-foreground">Loading accounts…</div>
                  ) : (overview?.accounts ?? []).length === 0 ? (
                    <div className="text-center py-6">
                      <p className="text-muted-foreground mb-3 text-sm">No accounts yet.</p>
                      <Button variant="financial" size="sm" onClick={() => navigate('/accounts')}>
                        <Plus className="w-4 h-4" /> Add Account
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {(overview?.accounts ?? []).map((account) => {
                        const Icon = ACCOUNT_TYPE_ICONS[account.account_type] ?? Wallet;
                        const isCredit = account.account_type === 'CREDIT';
                        return (
                          <div key={account.id} className="interactive-row flex items-center justify-between">
                            <div className="flex items-center space-x-3">
                              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                                isCredit ? 'bg-destructive-light text-destructive' : 'bg-success-light text-success'
                              }`}>
                                <Icon className="w-5 h-5" />
                              </div>
                              <div>
                                <div className="font-medium text-foreground">{account.name}</div>
                                <div className="text-xs text-muted-foreground">
                                  {ACCOUNT_TYPE_LABELS[account.account_type]}
                                  {account.institution ? ` · ${account.institution}` : ''}
                                </div>
                              </div>
                            </div>
                            <div className={`font-semibold ${isCredit ? 'text-destructive' : 'text-foreground'}`}>
                              {isCredit ? '-' : ''}{currency(account.balance, account.currency)}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </FinancialCardContent>
                <FinancialCardFooter>
                  <Button variant="financial" size="sm" className="w-full" onClick={() => navigate('/accounts')}>
                    <Plus className="w-4 h-4" />
                    Add Account
                  </Button>
                </FinancialCardFooter>
              </FinancialCard>

              {/* Combined transaction timeline */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">Combined Transaction Timeline</FinancialCardTitle>
                  <FinancialCardDescription>Recent activity across all accounts</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {overviewLoading ? (
                    <div className="text-sm text-muted-foreground">Loading…</div>
                  ) : (overview?.recent_transactions ?? []).length === 0 ? (
                    <div className="text-sm text-muted-foreground">No transactions yet.</div>
                  ) : (
                    <div className="space-y-3">
                      {(overview?.recent_transactions ?? []).slice(0, 10).map((txn) => {
                        const isIncome = txn.type === 'INCOME';
                        return (
                          <div key={txn.id} className="interactive-row flex items-center justify-between">
                            <div className="flex items-center space-x-3">
                              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                                isIncome ? 'bg-success-light text-success' : 'bg-destructive-light text-destructive'
                              }`}>
                                {isIncome ? <ArrowUpRight className="w-5 h-5" /> : <ArrowDownRight className="w-5 h-5" />}
                              </div>
                              <div>
                                <div className="font-medium text-foreground">{txn.description}</div>
                                <div className="text-sm text-muted-foreground">{new Date(txn.date).toLocaleDateString()}</div>
                              </div>
                            </div>
                            <div className={`font-semibold ${isIncome ? 'text-success' : 'text-foreground'}`}>
                              {isIncome ? '+' : '-'}{currency(Math.abs(txn.amount), txn.currency)}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            </div>

            {/* Spending breakdown */}
            <div>
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">Spending Breakdown</FinancialCardTitle>
                  <FinancialCardDescription>Across all accounts for {overview?.period?.month || month}</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {overviewLoading ? (
                    <div className="text-sm text-muted-foreground">Loading…</div>
                  ) : (overview?.spending_breakdown ?? []).length === 0 ? (
                    <div className="text-sm text-muted-foreground">No spending data for this period.</div>
                  ) : (
                    <div className="space-y-3">
                      {(overview?.spending_breakdown ?? []).slice(0, 8).map((row) => (
                        <div key={`${row.category_id ?? 'uncat'}-${row.category_name}`} className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-foreground">{row.category_name}</span>
                            <span className="text-muted-foreground">
                              {currency(row.amount)} ({row.share_pct.toFixed(0)}%)
                            </span>
                          </div>
                          <div className="chart-track h-2">
                            <div
                              className="chart-fill-primary h-2"
                              style={{ width: `${Math.max(2, Math.min(100, row.share_pct))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
