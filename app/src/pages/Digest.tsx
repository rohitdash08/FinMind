import { useEffect, useState } from 'react';
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
  ChevronLeft,
  ChevronRight,
  Lightbulb,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Wallet,
  BarChart3,
  History,
} from 'lucide-react';
import {
  getWeeklyDigestByDate,
  getDigestHistory,
  forceGenerateDigest,
  type WeeklyDigest as DigestType,
} from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function mondayOfWeek(d: Date): Date {
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function formatWeekRange(start: string, end: string): string {
  const s = new Date(start + 'T00:00:00');
  const e = new Date(end + 'T00:00:00');
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  return `${s.toLocaleDateString(undefined, opts)} - ${e.toLocaleDateString(undefined, { ...opts, year: 'numeric' })}`;
}

export function Digest() {
  const [digest, setDigest] = useState<DigestType | null>(null);
  const [history, setHistory] = useState<DigestType[]>([]);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentMonday, setCurrentMonday] = useState<Date>(() => mondayOfWeek(new Date()));

  const dateStr = currentMonday.toISOString().slice(0, 10);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getWeeklyDigestByDate(dateStr);
        setDigest(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load digest');
      } finally {
        setLoading(false);
      }
    })();
  }, [dateStr]);

  useEffect(() => {
    (async () => {
      try {
        const h = await getDigestHistory(8);
        setHistory(h);
      } catch {
        // non-critical
      }
    })();
  }, [digest]);

  const handlePrevWeek = () => {
    setCurrentMonday((prev) => {
      const d = new Date(prev);
      d.setDate(d.getDate() - 7);
      return d;
    });
  };

  const handleNextWeek = () => {
    const nextMonday = new Date(currentMonday);
    nextMonday.setDate(nextMonday.getDate() + 7);
    const today = mondayOfWeek(new Date());
    if (nextMonday <= today) {
      setCurrentMonday(nextMonday);
    }
  };

  const handleThisWeek = () => {
    setCurrentMonday(mondayOfWeek(new Date()));
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const res = await forceGenerateDigest();
      setDigest(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to regenerate');
    } finally {
      setRegenerating(false);
    }
  };

  const trends = digest?.trends;
  const topCategories = digest?.top_categories ?? [];

  const isCurrentWeek =
    currentMonday.toISOString().slice(0, 10) === mondayOfWeek(new Date()).toISOString().slice(0, 10);

  const summaryCards = [
    {
      title: 'Weekly Income',
      amount: currency(digest?.total_income ?? 0),
      change: trends
        ? `${trends.income_change_pct >= 0 ? '+' : ''}${trends.income_change_pct.toFixed(1)}%`
        : '--',
      trend: trends?.income_trend ?? 'flat',
      icon: TrendingUp,
      description: 'vs last week',
    },
    {
      title: 'Weekly Expenses',
      amount: currency(digest?.total_expenses ?? 0),
      change: trends
        ? `${trends.expense_change_pct >= 0 ? '+' : ''}${trends.expense_change_pct.toFixed(1)}%`
        : '--',
      trend: trends?.expense_trend === 'down' ? 'up' : 'down', // lower expenses is good
      icon: TrendingDown,
      description: 'vs last week',
    },
    {
      title: 'Net Flow',
      amount: currency(digest?.net_flow ?? 0),
      change: (digest?.net_flow ?? 0) >= 0 ? 'Positive' : 'Negative',
      trend: (digest?.net_flow ?? 0) >= 0 ? 'up' : 'down',
      icon: Wallet,
      description: 'This week',
    },
  ] as const;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              {digest
                ? formatWeekRange(digest.week_start, digest.week_end)
                : 'Smart financial summary'}
            </p>
          </div>
          <div className="flex gap-2 items-center">
            <Button variant="outline" size="sm" onClick={handlePrevWeek}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleThisWeek}
              disabled={isCurrentWeek}
            >
              This Week
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleNextWeek}
              disabled={isCurrentWeek}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
            {isCurrentWeek && (
              <Button
                variant="financial"
                size="sm"
                onClick={() => { void handleRegenerate(); }}
                disabled={regenerating}
              >
                <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} />
                {regenerating ? 'Generating...' : 'Refresh'}
              </Button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="error mb-6">{error}</div>
      )}

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3 mb-8">
        {summaryCards.map((card, index) => (
          <FinancialCard key={index} variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  {card.title}
                </FinancialCardTitle>
                <card.icon className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {loading ? '...' : card.amount}
              </div>
              <div className="flex items-center text-sm">
                {card.trend === 'up' ? (
                  <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                ) : card.trend === 'down' ? (
                  <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                ) : null}
                <span
                  className={
                    card.trend === 'up'
                      ? 'text-success font-medium mr-2'
                      : card.trend === 'down'
                        ? 'text-destructive font-medium mr-2'
                        : 'text-muted-foreground font-medium mr-2'
                  }
                >
                  {card.change}
                </span>
                <span className="text-muted-foreground">{card.description}</span>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Top Spending Categories */}
        <div className="lg:col-span-1">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-primary" />
                <FinancialCardTitle className="section-title">
                  Top Categories
                </FinancialCardTitle>
              </div>
              <FinancialCardDescription>Spending breakdown this week</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {loading ? (
                <div className="text-sm text-muted-foreground">Loading...</div>
              ) : topCategories.length === 0 ? (
                <div className="text-sm text-muted-foreground">No spending data this week.</div>
              ) : (
                <div className="space-y-3">
                  {topCategories.map((cat, i) => (
                    <div key={`${cat.category_id ?? 'uncat'}-${i}`} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-foreground">{cat.category_name}</span>
                        <span className="text-muted-foreground">
                          {currency(cat.amount)} ({cat.share_pct.toFixed(0)}%)
                        </span>
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

        {/* AI Insights */}
        <div className="lg:col-span-2">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center gap-2">
                <Lightbulb className="w-5 h-5 text-warning" />
                <FinancialCardTitle className="section-title">
                  AI Insights
                </FinancialCardTitle>
              </div>
              <FinancialCardDescription>
                Personalized analysis of your weekly finances
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {loading ? (
                <div className="text-sm text-muted-foreground">Analyzing your finances...</div>
              ) : digest?.ai_insights ? (
                <div className="prose prose-sm max-w-none text-foreground leading-relaxed whitespace-pre-wrap">
                  {digest.ai_insights}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  No insights available. Add some transactions to get started.
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Week-over-Week Comparison */}
          {trends && !loading && (
            <FinancialCard variant="financial" className="fade-in-up mt-6">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">
                  Week-over-Week Comparison
                </FinancialCardTitle>
                <FinancialCardDescription>
                  How this week compares to the previous one
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <div className="text-sm text-muted-foreground">Previous Week Income</div>
                    <div className="text-lg font-semibold text-foreground">
                      {currency(trends.previous_week_income)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-sm text-muted-foreground">Previous Week Expenses</div>
                    <div className="text-lg font-semibold text-foreground">
                      {currency(trends.previous_week_expenses)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-sm text-muted-foreground">Income Change</div>
                    <div className="flex items-center gap-1">
                      {trends.income_trend === 'up' ? (
                        <ArrowUpRight className="w-4 h-4 text-success" />
                      ) : trends.income_trend === 'down' ? (
                        <ArrowDownRight className="w-4 h-4 text-destructive" />
                      ) : null}
                      <span
                        className={`text-lg font-semibold ${
                          trends.income_trend === 'up'
                            ? 'text-success'
                            : trends.income_trend === 'down'
                              ? 'text-destructive'
                              : 'text-foreground'
                        }`}
                      >
                        {trends.income_change_pct >= 0 ? '+' : ''}
                        {trends.income_change_pct.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-sm text-muted-foreground">Expense Change</div>
                    <div className="flex items-center gap-1">
                      {trends.expense_trend === 'up' ? (
                        <ArrowUpRight className="w-4 h-4 text-destructive" />
                      ) : trends.expense_trend === 'down' ? (
                        <ArrowDownRight className="w-4 h-4 text-success" />
                      ) : null}
                      <span
                        className={`text-lg font-semibold ${
                          trends.expense_trend === 'down'
                            ? 'text-success'
                            : trends.expense_trend === 'up'
                              ? 'text-destructive'
                              : 'text-foreground'
                        }`}
                      >
                        {trends.expense_change_pct >= 0 ? '+' : ''}
                        {trends.expense_change_pct.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}
        </div>
      </div>

      {/* Past Digests */}
      {history.length > 0 && (
        <div className="mt-8">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center gap-2">
                <History className="w-5 h-5 text-primary" />
                <FinancialCardTitle className="section-title">
                  Past Digests
                </FinancialCardTitle>
              </div>
              <FinancialCardDescription>Browse your weekly financial history</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="space-y-2">
                {history.map((h) => {
                  const isActive = h.week_start === digest?.week_start;
                  return (
                    <button
                      key={h.id}
                      onClick={() => {
                        const d = new Date(h.week_start + 'T00:00:00');
                        setCurrentMonday(d);
                      }}
                      className={`w-full text-left interactive-row flex items-center justify-between p-3 rounded-lg transition ${
                        isActive ? 'bg-secondary' : 'hover:bg-muted'
                      }`}
                    >
                      <div>
                        <div className="font-medium text-foreground text-sm">
                          {formatWeekRange(h.week_start, h.week_end)}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Net: {currency(h.net_flow)}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-semibold text-foreground">
                          {currency(h.total_expenses)}
                        </div>
                        <div className="text-xs text-muted-foreground">spent</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </FinancialCardContent>
            <FinancialCardFooter />
          </FinancialCard>
        </div>
      )}
    </div>
  );
}
