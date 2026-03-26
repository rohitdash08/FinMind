import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  ArrowLeft,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  CheckCircle,
  Info,
  Wallet,
  BarChart3,
  Calendar,
  Lightbulb,
  Receipt,
} from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigest, type Trend, type Insight } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function getISOWeek(d: Date): string {
  const dt = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  dt.setUTCDate(dt.getUTCDate() + 4 - (dt.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(dt.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((dt.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${dt.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

function shiftWeek(week: string, delta: number): string {
  const [yearStr, weekStr] = week.split('-W');
  const year = parseInt(yearStr, 10);
  const weekNum = parseInt(weekStr, 10);
  // Approximate: find the Monday of the week and shift
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dayOfWeek = jan4.getUTCDay() || 7;
  const monday = new Date(jan4.getTime() + ((weekNum - 1) * 7 + 1 - dayOfWeek) * 86400000);
  monday.setUTCDate(monday.getUTCDate() + delta * 7);
  return getISOWeek(monday);
}

function TrendIcon({ direction }: { direction: string }) {
  switch (direction) {
    case 'UP': return <TrendingUp className="h-4 w-4 text-red-500" />;
    case 'DOWN': return <TrendingDown className="h-4 w-4 text-green-600" />;
    case 'FLAT': return <Minus className="h-4 w-4 text-muted-foreground" />;
    default: return <Info className="h-4 w-4 text-blue-500" />;
  }
}

function InsightIcon({ type }: { type: string }) {
  switch (type) {
    case 'positive': return <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />;
    case 'warning': return <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />;
    default: return <Info className="h-5 w-5 text-blue-500 shrink-0" />;
  }
}

function TrendBadge({ direction }: { direction: string }) {
  const variants: Record<string, string> = {
    UP: 'bg-red-100 text-red-700',
    DOWN: 'bg-green-100 text-green-700',
    FLAT: 'bg-gray-100 text-gray-600',
    NEW: 'bg-blue-100 text-blue-700',
    GONE: 'bg-purple-100 text-purple-700',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${variants[direction] || variants.FLAT}`}>
      {direction}
    </span>
  );
}

export default function Digest() {
  const [data, setData] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [week, setWeek] = useState(() => getISOWeek(new Date()));

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getWeeklyDigest({ week });
        setData(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load digest');
      } finally {
        setLoading(false);
      }
    })();
  }, [week]);

  const summary = data?.summary;
  const wow = data?.week_over_week;

  if (loading) {
    return (
      <div className="container-financial py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-muted-foreground animate-pulse text-lg">Loading weekly digest...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container-financial py-8">
        <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
          <AlertTriangle className="h-10 w-10 text-destructive" />
          <p className="text-destructive text-lg">{error}</p>
          <Button onClick={() => setWeek(getISOWeek(new Date()))}>Retry</Button>
        </div>
      </div>
    );
  }

  const maxDaily = Math.max(...(data?.daily_spending?.map(d => d.amount) || [0]), 1);

  return (
    <div className="container-financial py-8 space-y-6">
      {/* Header with week navigation */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Weekly Digest</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {data?.period?.start} to {data?.period?.end}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setWeek(w => shiftWeek(w, -1))}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Prev
          </Button>
          <span className="text-sm font-mono font-semibold px-3 py-1 bg-muted rounded-lg">
            {data?.week || week}
          </span>
          <Button variant="outline" size="sm" onClick={() => setWeek(w => shiftWeek(w, 1))}>
            Next <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Wallet className="h-4 w-4" /> Income
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{currency(summary?.total_income || 0)}</div>
            {wow?.income_change !== null && wow?.income_change !== undefined && (
              <p className={`text-xs mt-1 ${(wow.income_change || 0) >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                {(wow.income_change || 0) >= 0 ? '+' : ''}{wow.income_change}% vs last week
              </p>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Receipt className="h-4 w-4" /> Expenses
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{currency(summary?.total_expenses || 0)}</div>
            {wow?.expense_change !== null && wow?.expense_change !== undefined && (
              <p className={`text-xs mt-1 ${(wow.expense_change || 0) <= 0 ? 'text-green-600' : 'text-red-500'}`}>
                {(wow.expense_change || 0) >= 0 ? '+' : ''}{wow.expense_change}% vs last week
              </p>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <TrendingUp className="h-4 w-4" /> Net Savings
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className={`text-2xl font-bold ${(summary?.net_savings || 0) >= 0 ? 'text-green-700' : 'text-red-600'}`}>
              {currency(summary?.net_savings || 0)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {summary?.transaction_count || 0} transactions
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Calendar className="h-4 w-4" /> Upcoming Bills
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">
              {data?.upcoming_bills?.length || 0}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {currency(data?.upcoming_bills?.reduce((s, b) => s + b.amount, 0) || 0)} due
            </p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Daily Spending Pattern */}
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" /> Daily Spending
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-3">
              {data?.daily_spending?.map((day) => (
                <div key={day.date} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-12 shrink-0">{day.day_name.slice(0, 3)}</span>
                  <div className="flex-1">
                    <Progress value={maxDaily > 0 ? (day.amount / maxDaily) * 100 : 0} className="h-3" />
                  </div>
                  <span className="text-sm font-medium w-20 text-right">{currency(day.amount)}</span>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        {/* Category Breakdown */}
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" /> Category Breakdown
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {data?.category_breakdown?.length ? (
              <div className="space-y-3">
                {data.category_breakdown.map((cat) => (
                  <div key={cat.category_id ?? 'uncategorized'} className="flex items-center gap-3">
                    <span className="text-sm w-28 truncate shrink-0">{cat.category_name}</span>
                    <div className="flex-1">
                      <Progress value={cat.share_pct} className="h-3" />
                    </div>
                    <span className="text-sm font-medium w-20 text-right">{currency(cat.amount)}</span>
                    <span className="text-xs text-muted-foreground w-12 text-right">{cat.share_pct}%</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-6">No expenses this week</p>
            )}
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Trends */}
      {data?.trends && data.trends.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" /> Week-over-Week Trends
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="grid gap-3 sm:grid-cols-2">
              {data.trends.map((trend, i) => (
                <div key={i} className="flex items-start gap-3 rounded-lg border p-3">
                  <TrendIcon direction={trend.direction} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium truncate">{trend.metric.replace('category:', '')}</span>
                      <TrendBadge direction={trend.direction} />
                    </div>
                    <p className="text-xs text-muted-foreground">{trend.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Insights */}
      {data?.insights && data.insights.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5" /> Smart Insights
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-3">
              {data.insights.map((insight, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-3 rounded-lg p-3 ${
                    insight.type === 'positive' ? 'bg-green-50 border border-green-200' :
                    insight.type === 'warning' ? 'bg-amber-50 border border-amber-200' :
                    'bg-blue-50 border border-blue-200'
                  }`}
                >
                  <InsightIcon type={insight.type} />
                  <div>
                    <p className="text-sm font-semibold">{insight.title}</p>
                    <p className="text-sm text-muted-foreground mt-0.5">{insight.message}</p>
                  </div>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Upcoming Bills */}
      {data?.upcoming_bills && data.upcoming_bills.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5" /> Upcoming Bills (Next 7 Days)
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-2">
              {data.upcoming_bills.map((bill) => (
                <div key={bill.id} className="flex items-center justify-between rounded-lg border p-3">
                  <div>
                    <p className="text-sm font-medium">{bill.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Due {bill.due_date} &middot; {bill.cadence}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold">{currency(bill.amount, bill.currency)}</span>
                    {bill.autopay && (
                      <Badge variant="secondary" className="text-xs">Autopay</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}
    </div>
  );
}
