import { useEffect, useState, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  ArrowDownRight,
  ArrowUpRight,
  TrendingDown,
  TrendingUp,
  Minus,
  Wallet,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  CheckCircle,
  Info,
  BarChart3,
  Calendar,
} from 'lucide-react';
import { fetchWeeklyDigest, type WeeklyDigest } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function getISOWeek(d: Date): string {
  const date = new Date(d.getTime());
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + 3 - ((date.getDay() + 6) % 7));
  const week1 = new Date(date.getFullYear(), 0, 4);
  const weekNum =
    1 +
    Math.round(
      ((date.getTime() - week1.getTime()) / 86400000 -
        3 +
        ((week1.getDay() + 6) % 7)) /
        7,
    );
  return `${date.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

function shiftWeek(week: string, delta: number): string {
  const parts = week.split('-W');
  const year = parseInt(parts[0]);
  const wk = parseInt(parts[1]);
  const monday = new Date(year, 0, 4);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7) + (wk - 1) * 7 + delta * 7);
  return getISOWeek(monday);
}

const insightIcon = {
  warning: AlertTriangle,
  positive: CheckCircle,
  info: Info,
};

const insightColor = {
  warning: 'text-destructive bg-destructive-light',
  positive: 'text-success bg-success-light',
  info: 'text-primary bg-primary/10',
};

export function Digest() {
  const [week, setWeek] = useState(() => getISOWeek(new Date()));
  const [data, setData] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDigest = useCallback(async (w: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWeeklyDigest(w);
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load digest');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDigest(week);
  }, [week, loadDigest]);

  const goToPrevWeek = () => setWeek((w) => shiftWeek(w, -1));
  const goToNextWeek = () => setWeek((w) => shiftWeek(w, 1));
  const goToCurrentWeek = () => setWeek(getISOWeek(new Date()));

  const summary = data?.summary ?? {
    total_income: 0,
    total_expenses: 0,
    net_flow: 0,
    transaction_count: 0,
  };
  const wow = data?.week_over_week;
  const trendIcon =
    data?.trends?.spending_direction === 'up'
      ? TrendingUp
      : data?.trends?.spending_direction === 'down'
        ? TrendingDown
        : Minus;

  const TrendIcon = trendIcon;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              {data?.period
                ? `${new Date(data.period.start).toLocaleDateString()} — ${new Date(data.period.end).toLocaleDateString()}`
                : 'Loading...'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={goToPrevWeek} aria-label="Previous week">
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm font-mono font-medium min-w-[90px] text-center">
              {week}
            </span>
            <Button variant="outline" size="sm" onClick={goToNextWeek} aria-label="Next week">
              <ChevronRight className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={goToCurrentWeek}>
              <Calendar className="w-4 h-4" />
              This Week
            </Button>
          </div>
        </div>
      </div>

      {error && (
        <div className="error mb-6">{error}</div>
      )}

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
        <FinancialCard variant="financial" className="group card-interactive fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Expenses
              </FinancialCardTitle>
              <TrendIcon className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : currency(summary.total_expenses)}
            </div>
            {wow && (
              <div className="flex items-center text-sm">
                {wow.expense_pct_change > 0 ? (
                  <ArrowUpRight className="w-4 h-4 text-destructive mr-1" />
                ) : wow.expense_pct_change < 0 ? (
                  <ArrowDownRight className="w-4 h-4 text-success mr-1" />
                ) : null}
                <span
                  className={`font-medium mr-2 ${
                    wow.expense_pct_change > 0
                      ? 'text-destructive'
                      : wow.expense_pct_change < 0
                        ? 'text-success'
                        : 'text-muted-foreground'
                  }`}
                >
                  {wow.expense_pct_change > 0 ? '+' : ''}
                  {wow.expense_pct_change}%
                </span>
                <span className="text-muted-foreground">vs last week</span>
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="group card-interactive fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Income
              </FinancialCardTitle>
              <TrendingUp className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : currency(summary.total_income)}
            </div>
            {wow && (
              <div className="flex items-center text-sm">
                <span className="text-muted-foreground">
                  Last week: {currency(wow.previous_week_income)}
                </span>
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>

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
            <div
              className={`metric-value mb-1 ${
                summary.net_flow >= 0 ? 'text-success' : 'text-destructive'
              }`}
            >
              {loading ? '...' : currency(summary.net_flow)}
            </div>
            <div className="text-sm text-muted-foreground">
              {summary.net_flow >= 0 ? 'Surplus' : 'Deficit'} this week
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="group card-interactive fade-in-up">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Transactions
              </FinancialCardTitle>
              <BarChart3 className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : summary.transaction_count}
            </div>
            <div className="text-sm text-muted-foreground">
              Total entries this week
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Left column: Daily + Categories */}
        <div className="lg:col-span-2 space-y-6">
          {/* Daily Spending Bar */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">
                Daily Spending
              </FinancialCardTitle>
              <FinancialCardDescription>
                Spending distribution across the week
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.daily_spending ? (
                <div className="space-y-2">
                  {(() => {
                    const maxAmount = Math.max(
                      ...data.daily_spending.map((d) => d.amount),
                      1,
                    );
                    return data.daily_spending.map((day) => {
                      const pct = (day.amount / maxAmount) * 100;
                      return (
                        <div key={day.date} className="flex items-center gap-3">
                          <span className="text-sm text-muted-foreground w-20 shrink-0">
                            {day.day_name.slice(0, 3)}
                          </span>
                          <div className="flex-1">
                            <Progress value={pct} className="h-3" />
                          </div>
                          <span className="text-sm font-medium w-24 text-right">
                            {currency(day.amount)}
                          </span>
                        </div>
                      );
                    });
                  })()}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  No data available.
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Category Breakdown */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">
                Category Breakdown
              </FinancialCardTitle>
              <FinancialCardDescription>
                Expense mix with week-over-week changes
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {(data?.category_breakdown?.length ?? 0) === 0 ? (
                <div className="text-sm text-muted-foreground">
                  No category data for this week.
                </div>
              ) : (
                <div className="space-y-4">
                  {data!.category_breakdown.map((cat) => (
                    <div
                      key={`${cat.category_id ?? 'uncat'}-${cat.category_name}`}
                      className="space-y-1"
                    >
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className="text-foreground font-medium">
                            {cat.category_name}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            ({cat.count} items)
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-foreground">
                            {currency(cat.amount)} ({cat.share_pct}%)
                          </span>
                          {cat.wow_delta !== 0 && (
                            <span
                              className={`text-xs font-medium ${
                                cat.wow_delta > 0
                                  ? 'text-destructive'
                                  : 'text-success'
                              }`}
                            >
                              {cat.wow_delta > 0 ? '+' : ''}
                              {currency(cat.wow_delta)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="chart-track h-2">
                        <div
                          className="chart-fill-primary h-2"
                          style={{
                            width: `${Math.max(2, Math.min(100, cat.share_pct))}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>

        {/* Right column: Insights + Top Transactions */}
        <div className="space-y-6">
          {/* Insights */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">
                Insights
              </FinancialCardTitle>
              <FinancialCardDescription>
                Smart observations about your finances
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {(data?.insights?.length ?? 0) === 0 ? (
                <div className="text-sm text-muted-foreground">
                  No insights this week. Add more transactions!
                </div>
              ) : (
                <div className="space-y-3">
                  {data!.insights.map((insight, i) => {
                    const Icon = insightIcon[insight.type];
                    const colorClass = insightColor[insight.type];
                    return (
                      <div
                        key={`${insight.type}-${insight.title}`}
                        className="interactive-row flex items-start gap-3"
                      >
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${colorClass}`}
                        >
                          <Icon className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="font-medium text-foreground text-sm">
                            {insight.title}
                          </div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {insight.message}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Top Transactions */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">
                Top Expenses
              </FinancialCardTitle>
              <FinancialCardDescription>
                Highest spending items this week
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {(data?.top_transactions?.length ?? 0) === 0 ? (
                <div className="text-sm text-muted-foreground">
                  No expenses this week.
                </div>
              ) : (
                <div className="space-y-3">
                  {data!.top_transactions.map((tx) => (
                    <div
                      key={tx.id}
                      className="interactive-row flex items-center justify-between"
                    >
                      <div>
                        <div className="font-medium text-foreground text-sm">
                          {tx.description}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {new Date(tx.date).toLocaleDateString()}
                        </div>
                      </div>
                      <div className="font-semibold text-foreground">
                        {currency(tx.amount)}
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
