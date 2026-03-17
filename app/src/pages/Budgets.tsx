import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Calendar,
  DollarSign,
  PieChart,
  TrendingDown,
  TrendingUp,
  Target,
  AlertCircle,
  Minus,
  ShieldCheck,
  BarChart3,
  RefreshCw,
  Info,
} from 'lucide-react';
import {
  getBudgetSuggestion,
  type BudgetSuggestion,
  type CategorySuggestion,
} from '@/api/insights';

function currency(n: number) {
  return `$${Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function confidenceColor(label: string) {
  switch (label) {
    case 'very_high':
      return 'text-success';
    case 'high':
      return 'text-success';
    case 'medium':
      return 'text-warning';
    case 'low':
      return 'text-destructive';
    default:
      return 'text-muted-foreground';
  }
}

function confidenceBadgeVariant(label: string) {
  switch (label) {
    case 'very_high':
    case 'high':
      return 'default' as const;
    case 'medium':
      return 'secondary' as const;
    default:
      return 'destructive' as const;
  }
}

function trendIcon(direction: string) {
  if (direction === 'increasing') return <TrendingUp className="w-3 h-3 text-destructive" />;
  if (direction === 'decreasing') return <TrendingDown className="w-3 h-3 text-success" />;
  return <Minus className="w-3 h-3 text-muted-foreground" />;
}

function trendColor(direction: string) {
  if (direction === 'increasing') return 'text-destructive';
  if (direction === 'decreasing') return 'text-success';
  return 'text-muted-foreground';
}

const CATEGORY_COLORS = [
  'bg-primary',
  'bg-success',
  'bg-destructive',
  'bg-accent',
  'bg-warning',
  'bg-secondary',
];

export function Budgets() {
  const [data, setData] = useState<BudgetSuggestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lookback, setLookback] = useState(6);
  const [month] = useState(() => new Date().toISOString().slice(0, 7));

  const fetchSuggestion = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getBudgetSuggestion({ month, months: lookback });
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load budget suggestions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSuggestion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, lookback]);

  const confidence = data?.confidence;
  const breakdown = data?.breakdown;
  const suggestedTotal = data?.suggested_total ?? 0;
  const categories = data?.category_suggestions ?? [];
  const spendingTrend = data?.spending_trend;
  const dataRange = data?.data_range;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Smart Budget Suggestions</h1>
            <p className="page-subtitle">
              AI-powered recommendations based on your spending history
            </p>
          </div>
          <div className="flex gap-3">
            <Button
              variant={lookback === 3 ? 'financial' : 'outline'}
              size="sm"
              onClick={() => setLookback(3)}
            >
              <Calendar className="w-4 h-4" />
              3 Months
            </Button>
            <Button
              variant={lookback === 6 ? 'financial' : 'outline'}
              size="sm"
              onClick={() => setLookback(6)}
            >
              <Calendar className="w-4 h-4" />
              6 Months
            </Button>
            <Button variant="outline" size="sm" onClick={fetchSuggestion}>
              <RefreshCw className="w-4 h-4" />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      {error && (
        <div className="error mb-6">{error}. Showing empty fallback state.</div>
      )}

      {/* Confidence & Data Range Banner */}
      {!loading && data && (
        <div className="mb-6">
          <FinancialCard variant="financial" size="sm">
            <FinancialCardContent>
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <ShieldCheck className={`w-4 h-4 ${confidenceColor(confidence?.label ?? 'no_data')}`} />
                  <span className="text-muted-foreground">Confidence:</span>
                  <Badge variant={confidenceBadgeVariant(confidence?.label ?? 'no_data')}>
                    {confidence?.label?.replace('_', ' ') ?? 'N/A'} ({((confidence?.score ?? 0) * 100).toFixed(0)}%)
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Data:</span>
                  <span className="text-foreground font-medium">
                    {dataRange?.months_with_data ?? 0} of {dataRange?.months_requested ?? lookback} months
                  </span>
                  {dataRange?.oldest_month && dataRange?.newest_month && (
                    <span className="text-muted-foreground">
                      ({dataRange.oldest_month} to {dataRange.newest_month})
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Info className="w-4 h-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Method:</span>
                  <span className="text-foreground font-medium capitalize">{data.method?.replace('_', ' ')}</span>
                </div>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Budget Overview Cards */}
      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Suggested Budget
              </FinancialCardTitle>
              <Target className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            {loading ? (
              <Skeleton className="h-8 w-32" />
            ) : (
              <>
                <div className="metric-value text-foreground mb-1">
                  {currency(suggestedTotal)}
                </div>
                <div className="text-sm text-muted-foreground">
                  Target for {data?.month ?? month}
                </div>
              </>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Spending Trend
              </FinancialCardTitle>
              {spendingTrend?.direction === 'increasing' ? (
                <TrendingUp className="w-5 h-5 text-destructive" />
              ) : spendingTrend?.direction === 'decreasing' ? (
                <TrendingDown className="w-5 h-5 text-success" />
              ) : (
                <DollarSign className="w-5 h-5 text-muted-foreground" />
              )}
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            {loading ? (
              <Skeleton className="h-8 w-32" />
            ) : (
              <>
                <div className="metric-value text-foreground mb-1">
                  {spendingTrend ? (
                    <span className={trendColor(spendingTrend.direction)}>
                      {spendingTrend.change_pct > 0 ? '+' : ''}
                      {spendingTrend.change_pct}%
                    </span>
                  ) : (
                    'N/A'
                  )}
                </div>
                <div className="text-sm text-muted-foreground">
                  {spendingTrend?.direction === 'increasing'
                    ? 'Spending is rising'
                    : spendingTrend?.direction === 'decreasing'
                    ? 'Spending is falling'
                    : 'Spending is stable'}
                </div>
              </>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={suggestedTotal > 0 ? 'success' : 'financial'}>
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">
                50/30/20 Breakdown
              </FinancialCardTitle>
              <PieChart className="w-5 h-5" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
              </div>
            ) : breakdown ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span>Needs (50%)</span>
                  <span className="font-semibold">{currency(breakdown.needs)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Wants (30%)</span>
                  <span className="font-semibold">{currency(breakdown.wants)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Savings (20%)</span>
                  <span className="font-semibold">{currency(breakdown.savings)}</span>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">No data available</div>
            )}
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Category Suggestions + Monthly Spending History */}
      <div className="grid gap-6 lg:grid-cols-3 mb-8">
        <div className="lg:col-span-2">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="section-title">
                  Category Budget Suggestions
                </FinancialCardTitle>
                {categories.length > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {categories.length} categories
                  </Badge>
                )}
              </div>
              <FinancialCardDescription>
                Per-category limits based on your spending patterns
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {loading ? (
                <div className="space-y-4">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="space-y-2">
                      <Skeleton className="h-5 w-full" />
                      <Skeleton className="h-3 w-full" />
                    </div>
                  ))}
                </div>
              ) : categories.length === 0 ? (
                <div className="text-center py-8">
                  <AlertCircle className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground">
                    No spending data found for the selected period.
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Add expenses to get personalized budget suggestions.
                  </p>
                </div>
              ) : (
                <div className="space-y-6">
                  {categories.map((cat: CategorySuggestion, index: number) => {
                    const colorClass = CATEGORY_COLORS[index % CATEGORY_COLORS.length];
                    const pctOfTotal =
                      suggestedTotal > 0
                        ? (cat.suggested_limit / suggestedTotal) * 100
                        : 0;

                    return (
                      <div key={cat.category_id ?? `cat-${index}`} className="space-y-3 interactive-row">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <div className={`w-4 h-4 rounded-full ${colorClass}`} />
                            <div>
                              <div className="font-medium text-foreground">
                                {cat.category_name}
                              </div>
                              <div className="text-sm text-muted-foreground">
                                Avg {currency(cat.average_spending)}/mo
                                <span className="mx-1">&middot;</span>
                                {cat.months_with_data} month{cat.months_with_data !== 1 ? 's' : ''} of data
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-semibold text-foreground">
                              {currency(cat.suggested_limit)}
                            </div>
                            <div className="flex items-center justify-end gap-1 text-sm">
                              {trendIcon(cat.trend_direction)}
                              <span className={trendColor(cat.trend_direction)}>
                                {cat.trend_pct > 0 ? '+' : ''}
                                {cat.trend_pct}%
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="chart-track">
                          <div
                            className={
                              cat.trend_direction === 'increasing'
                                ? 'chart-fill-danger'
                                : 'chart-fill-primary'
                            }
                            style={{ width: `${Math.min(pctOfTotal, 100)}%` }}
                          />
                        </div>
                        {cat.trend_direction === 'increasing' && cat.trend_pct > 10 && (
                          <Badge variant="destructive" className="text-xs">
                            Spending rising fast
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>

        {/* Monthly Spending History Sidebar */}
        <div>
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">
                Monthly Spending History
              </FinancialCardTitle>
              <FinancialCardDescription>
                Total spending per month used in analysis
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {loading ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : data?.monthly_totals ? (
                <MonthlyHistoryBars
                  totals={data.monthly_totals}
                  suggestedTotal={suggestedTotal}
                />
              ) : (
                <div className="text-sm text-muted-foreground">
                  No monthly data available.
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Tips (from OpenAI) */}
          {data?.tips && data.tips.length > 0 && (
            <FinancialCard variant="financial" className="fade-in-up mt-6">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">
                  Budget Tips
                </FinancialCardTitle>
                <FinancialCardDescription>
                  AI-generated recommendations
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="space-y-3">
                  {data.tips.map((tip, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-sm text-foreground"
                    >
                      <span className="text-primary font-bold mt-0.5">{i + 1}.</span>
                      {tip}
                    </li>
                  ))}
                </ul>
              </FinancialCardContent>
            </FinancialCard>
          )}
        </div>
      </div>
    </div>
  );
}

function MonthlyHistoryBars({
  totals,
  suggestedTotal,
}: {
  totals: Record<string, number>;
  suggestedTotal: number;
}) {
  const entries = Object.entries(totals).sort(([a], [b]) => a.localeCompare(b));
  const maxVal = Math.max(suggestedTotal, ...entries.map(([, v]) => v), 1);

  return (
    <div className="space-y-3">
      {entries.map(([ym, amount]) => {
        const pct = (amount / maxVal) * 100;
        const isAboveSuggested = amount > suggestedTotal && suggestedTotal > 0;
        return (
          <div key={ym} className="space-y-1">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{ym}</span>
              <span
                className={`font-medium ${isAboveSuggested ? 'text-destructive' : 'text-foreground'}`}
              >
                {currency(amount)}
              </span>
            </div>
            <div className="chart-track h-2">
              <div
                className={`h-2 ${isAboveSuggested ? 'chart-fill-danger' : 'chart-fill-primary'}`}
                style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
              />
            </div>
          </div>
        );
      })}
      {suggestedTotal > 0 && (
        <div className="flex items-center gap-2 pt-2 border-t border-border text-xs text-muted-foreground">
          <Target className="w-3 h-3" />
          Suggested: {currency(suggestedTotal)}
        </div>
      )}
    </div>
  );
}
