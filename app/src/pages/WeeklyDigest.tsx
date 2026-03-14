import { useEffect, useState, useMemo } from 'react';
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
  TrendingDown,
  TrendingUp,
  Wallet,
  PiggyBank,
  BarChart3,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Info,
  Receipt,
  Zap,
  History,
} from 'lucide-react';
import {
  getWeeklyDigest,
  getDigestHistory,
  type WeeklyDigestResponse,
  type DigestHistoryItem,
  type DigestInsight,
} from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function formatDate(iso: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

function formatWeekRange(start: string, end: string) {
  return `${formatDate(start)} - ${formatDate(end)}`;
}

function getMonday(d: Date): Date {
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function isoDate(d: Date): string {
  return d.toISOString().split('T')[0];
}

function InsightBadge({ insight }: { insight: DigestInsight }) {
  const iconMap = {
    success: <CheckCircle2 className="w-4 h-4 text-success" />,
    warning: <AlertTriangle className="w-4 h-4 text-warning" />,
    info: <Info className="w-4 h-4 text-primary" />,
  };
  const bgMap = {
    success: 'bg-success-light border-success/20',
    warning: 'bg-warning-light border-warning/20',
    info: 'bg-primary-light/10 border-primary/20',
  };

  return (
    <div className={`rounded-xl border p-4 ${bgMap[insight.type]}`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5">{iconMap[insight.type]}</div>
        <div>
          <div className="font-semibold text-sm text-foreground">{insight.title}</div>
          <div className="text-sm text-muted-foreground mt-0.5">{insight.message}</div>
        </div>
      </div>
    </div>
  );
}

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="chart-track h-2.5 rounded-full">
      <div
        className={`h-2.5 rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.max(2, pct)}%` }}
      />
    </div>
  );
}

export default function WeeklyDigest() {
  const [digest, setDigest] = useState<WeeklyDigestResponse | null>(null);
  const [history, setHistory] = useState<DigestHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentMonday, setCurrentMonday] = useState(() => getMonday(new Date()));
  const [showHistory, setShowHistory] = useState(false);

  const fetchDigest = async (monday: Date) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getWeeklyDigest(isoDate(monday));
      setDigest(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load digest');
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await getDigestHistory(12);
      setHistory(res);
    } catch {
      // silently fail for history
    }
  };

  useEffect(() => {
    fetchDigest(currentMonday);
    fetchHistory();
  }, [currentMonday]);

  const navigateWeek = (direction: number) => {
    const newMonday = new Date(currentMonday);
    newMonday.setDate(newMonday.getDate() + direction * 7);
    setCurrentMonday(newMonday);
  };

  const goToCurrentWeek = () => {
    setCurrentMonday(getMonday(new Date()));
  };

  const summary = digest?.summary;
  const overview = summary?.overview;
  const comparison = summary?.comparison;

  const maxDailySpend = useMemo(() => {
    if (!summary?.daily_breakdown) return 0;
    return Math.max(...summary.daily_breakdown.map((d) => d.expenses), 1);
  }, [summary]);

  const maxCategoryAmount = useMemo(() => {
    if (!summary?.category_breakdown?.length) return 0;
    return Math.max(...summary.category_breakdown.map((c) => c.amount), 1);
  }, [summary]);

  const trendMax = useMemo(() => {
    if (!summary?.trend?.length) return 0;
    return Math.max(...summary.trend.map((w) => Math.max(w.expenses, w.income)), 1);
  }, [summary]);

  if (showHistory) {
    return (
      <div className="page-wrap">
        <div className="page-header">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="page-title">Digest History</h1>
              <p className="page-subtitle">Browse your past weekly financial digests.</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => setShowHistory(false)}>
              <ChevronLeft className="w-4 h-4" />
              Back to Digest
            </Button>
          </div>
        </div>

        <div className="space-y-3">
          {history.length === 0 ? (
            <FinancialCard variant="financial">
              <FinancialCardContent>
                <div className="text-sm text-muted-foreground py-8 text-center">
                  No digest history yet. Generate your first weekly digest to get started.
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ) : (
            history.map((item) => (
              <FinancialCard
                key={item.id}
                variant="financial"
                className="card-interactive cursor-pointer"
                onClick={() => {
                  setCurrentMonday(new Date(item.week_start + 'T00:00:00'));
                  setShowHistory(false);
                }}
              >
                <FinancialCardContent>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-primary-light/20 flex items-center justify-center">
                        <CalendarDays className="w-5 h-5 text-primary" />
                      </div>
                      <div>
                        <div className="font-semibold text-foreground">
                          {formatWeekRange(item.week_start, item.week_end)}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Generated{' '}
                          {item.generated_at
                            ? new Date(item.generated_at).toLocaleDateString()
                            : 'N/A'}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-foreground">
                        {currency(item.summary?.overview?.total_expenses || 0)} spent
                      </div>
                      <div
                        className={`text-xs font-medium ${
                          (item.summary?.overview?.net_flow || 0) >= 0
                            ? 'text-success'
                            : 'text-destructive'
                        }`}
                      >
                        {(item.summary?.overview?.net_flow || 0) >= 0 ? '+' : ''}
                        {currency(item.summary?.overview?.net_flow || 0)} net
                      </div>
                    </div>
                  </div>
                </FinancialCardContent>
              </FinancialCard>
            ))
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="page-header">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              {summary
                ? formatWeekRange(summary.period.week_start, summary.period.week_end)
                : 'Your weekly financial summary'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => navigateWeek(-1)}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={goToCurrentWeek}>
              <CalendarDays className="w-4 h-4" />
              This Week
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigateWeek(1)}>
              <ChevronRight className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => fetchDigest(currentMonday)}>
              <RefreshCw className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowHistory(true)}>
              <History className="w-4 h-4" />
              History
            </Button>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
          {[1, 2, 3, 4].map((i) => (
            <FinancialCard key={i} variant="financial" className="animate-pulse">
              <FinancialCardContent>
                <div className="h-20 bg-muted/50 rounded-lg" />
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
            {/* Net Flow */}
            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                    Net Flow
                  </FinancialCardTitle>
                  <Wallet className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {currency(overview?.net_flow || 0)}
                </div>
                <div className="flex items-center text-sm">
                  {(overview?.net_flow || 0) >= 0 ? (
                    <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                  ) : (
                    <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                  )}
                  <span
                    className={
                      (overview?.net_flow || 0) >= 0
                        ? 'text-success font-medium'
                        : 'text-destructive font-medium'
                    }
                  >
                    {(overview?.net_flow || 0) >= 0 ? 'Surplus' : 'Deficit'}
                  </span>
                </div>
              </FinancialCardContent>
            </FinancialCard>

            {/* Total Spending */}
            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                    Total Spending
                  </FinancialCardTitle>
                  <TrendingDown className="w-5 h-5 text-muted-foreground group-hover:text-destructive transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {currency(overview?.total_expenses || 0)}
                </div>
                <div className="flex items-center text-sm">
                  {comparison?.spending_change_pct !== null &&
                  comparison?.spending_change_pct !== undefined ? (
                    <>
                      {comparison.spending_change_pct > 0 ? (
                        <ArrowUpRight className="w-4 h-4 text-destructive mr-1" />
                      ) : (
                        <ArrowDownRight className="w-4 h-4 text-success mr-1" />
                      )}
                      <span
                        className={
                          comparison.spending_change_pct > 0
                            ? 'text-destructive font-medium mr-2'
                            : 'text-success font-medium mr-2'
                        }
                      >
                        {comparison.spending_change_pct > 0 ? '+' : ''}
                        {comparison.spending_change_pct.toFixed(1)}%
                      </span>
                      <span className="text-muted-foreground">vs last week</span>
                    </>
                  ) : (
                    <span className="text-muted-foreground">No prior week data</span>
                  )}
                </div>
              </FinancialCardContent>
            </FinancialCard>

            {/* Savings Rate */}
            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                    Savings Rate
                  </FinancialCardTitle>
                  <PiggyBank className="w-5 h-5 text-muted-foreground group-hover:text-success transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {overview?.savings_rate !== null && overview?.savings_rate !== undefined
                    ? `${overview.savings_rate.toFixed(1)}%`
                    : '--'}
                </div>
                <div className="flex items-center text-sm">
                  {overview?.savings_rate !== null && overview?.savings_rate !== undefined ? (
                    <>
                      {overview.savings_rate >= 20 ? (
                        <CheckCircle2 className="w-4 h-4 text-success mr-1" />
                      ) : (
                        <Info className="w-4 h-4 text-primary mr-1" />
                      )}
                      <span className="text-muted-foreground">
                        {overview.savings_rate >= 20 ? 'On track' : 'Target: 20%+'}
                      </span>
                    </>
                  ) : (
                    <span className="text-muted-foreground">No income recorded</span>
                  )}
                </div>
              </FinancialCardContent>
            </FinancialCard>

            {/* Transactions */}
            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                    Transactions
                  </FinancialCardTitle>
                  <Receipt className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {overview?.transaction_count || 0}
                </div>
                <div className="flex items-center text-sm">
                  <Zap className="w-4 h-4 text-primary mr-1" />
                  <span className="text-muted-foreground">
                    Avg {currency(overview?.avg_daily_spending || 0)}/day
                  </span>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* Main Content Grid */}
          <div className="grid lg:grid-cols-3 gap-8 mb-8">
            {/* Left Column: Charts */}
            <div className="lg:col-span-2 space-y-6">
              {/* Daily Spending Chart */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <div className="flex items-center justify-between">
                    <FinancialCardTitle className="section-title">Daily Spending</FinancialCardTitle>
                    <BarChart3 className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <FinancialCardDescription>
                    Expense distribution across the week
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <div className="space-y-3">
                    {summary?.daily_breakdown?.map((day) => (
                      <div key={day.date} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-foreground font-medium w-20">
                            {day.day_name.slice(0, 3)}
                          </span>
                          <span className="text-muted-foreground">
                            {currency(day.expenses)}
                            {day.income > 0 && (
                              <span className="text-success ml-2">+{currency(day.income)}</span>
                            )}
                          </span>
                        </div>
                        <MiniBar value={day.expenses} max={maxDailySpend} color="chart-fill-primary" />
                      </div>
                    ))}
                  </div>
                </FinancialCardContent>
              </FinancialCard>

              {/* 3-Week Trend */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <div className="flex items-center justify-between">
                    <FinancialCardTitle className="section-title">
                      3-Week Trend
                    </FinancialCardTitle>
                    <TrendingUp className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <FinancialCardDescription>
                    Rolling spending and income comparison
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <div className="space-y-4">
                    {summary?.trend?.map((week, idx) => {
                      const isCurrentWeek = idx === (summary?.trend?.length || 1) - 1;
                      return (
                        <div
                          key={week.week_start}
                          className={`rounded-xl p-4 ${
                            isCurrentWeek
                              ? 'bg-primary-light/10 border border-primary/20'
                              : 'bg-muted/30'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <span className="text-sm font-medium text-foreground">
                              {formatWeekRange(week.week_start, week.week_end)}
                              {isCurrentWeek && (
                                <span className="ml-2 text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">
                                  Current
                                </span>
                              )}
                            </span>
                            <span
                              className={`text-sm font-semibold ${
                                week.net >= 0 ? 'text-success' : 'text-destructive'
                              }`}
                            >
                              {week.net >= 0 ? '+' : ''}
                              {currency(week.net)}
                            </span>
                          </div>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <div className="text-xs text-muted-foreground mb-1">Income</div>
                              <MiniBar value={week.income} max={trendMax} color="bg-success" />
                              <div className="text-xs text-success mt-1">{currency(week.income)}</div>
                            </div>
                            <div>
                              <div className="text-xs text-muted-foreground mb-1">Expenses</div>
                              <MiniBar value={week.expenses} max={trendMax} color="bg-destructive" />
                              <div className="text-xs text-destructive mt-1">
                                {currency(week.expenses)}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </FinancialCardContent>
              </FinancialCard>

              {/* Income vs Expenses Comparison */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">
                    Week-over-Week Comparison
                  </FinancialCardTitle>
                  <FinancialCardDescription>
                    This week vs previous week
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <div className="grid grid-cols-2 gap-6">
                    <div className="space-y-4">
                      <div className="text-center">
                        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                          This Week
                        </div>
                        <div className="text-lg font-bold text-foreground">
                          {currency(overview?.total_expenses || 0)}
                        </div>
                        <div className="text-xs text-success">
                          Income: {currency(overview?.total_income || 0)}
                        </div>
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="text-center">
                        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                          Previous Week
                        </div>
                        <div className="text-lg font-bold text-foreground">
                          {currency(comparison?.prev_week_expenses || 0)}
                        </div>
                        <div className="text-xs text-success">
                          Income: {currency(comparison?.prev_week_income || 0)}
                        </div>
                      </div>
                    </div>
                  </div>
                </FinancialCardContent>
              </FinancialCard>
            </div>

            {/* Right Column: Breakdown & Insights */}
            <div className="space-y-6">
              {/* Category Breakdown */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">
                    Category Breakdown
                  </FinancialCardTitle>
                  <FinancialCardDescription>Where your money went</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {!summary?.category_breakdown?.length ? (
                    <div className="text-sm text-muted-foreground py-4 text-center">
                      No expenses this week.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {summary.category_breakdown.map((cat) => (
                        <div
                          key={`${cat.category_id ?? 'uncat'}-${cat.category_name}`}
                          className="space-y-1"
                        >
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-foreground font-medium">{cat.category_name}</span>
                            <span className="text-muted-foreground">
                              {currency(cat.amount)} ({cat.share_pct.toFixed(0)}%)
                            </span>
                          </div>
                          <MiniBar
                            value={cat.amount}
                            max={maxCategoryAmount}
                            color="chart-fill-primary"
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>

              {/* Biggest Expense */}
              {summary?.biggest_expense && (
                <FinancialCard variant="warning" className="fade-in-up">
                  <FinancialCardHeader className="pb-2">
                    <FinancialCardTitle className="text-sm font-semibold text-foreground">
                      Biggest Expense
                    </FinancialCardTitle>
                  </FinancialCardHeader>
                  <FinancialCardContent>
                    <div className="text-lg font-bold text-foreground">
                      {currency(summary.biggest_expense.amount)}
                    </div>
                    <div className="text-sm text-muted-foreground mt-1">
                      {summary.biggest_expense.description}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {formatDate(summary.biggest_expense.date)}
                    </div>
                  </FinancialCardContent>
                </FinancialCard>
              )}

              {/* Smart Insights */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">Smart Insights</FinancialCardTitle>
                  <FinancialCardDescription>AI-powered observations</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {!summary?.insights?.length ? (
                    <div className="text-sm text-muted-foreground py-4 text-center">
                      Add more transactions to unlock insights.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {summary.insights.map((insight, idx) => (
                        <InsightBadge key={idx} insight={insight} />
                      ))}
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
