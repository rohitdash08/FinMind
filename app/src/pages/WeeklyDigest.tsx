import { useEffect, useMemo, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ArrowDownRight,
  ArrowUpRight,
  Calendar,
  TrendingDown,
  TrendingUp,
  Wallet,
  PieChart,
  Lightbulb,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { getWeeklySummary, type WeeklySummary } from '@/api/weekly-summary';
import { formatMoney } from '@/lib/currency';
import { cn } from '@/lib/utils';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

function getWeekLabel(weekStart: string) {
  const start = new Date(weekStart);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  return `${formatDate(weekStart)} - ${formatDate(end.toISOString().split('T')[0])}`;
}

export function WeeklyDigest() {
  const [data, setData] = useState<WeeklySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [weekOffset, setWeekOffset] = useState(0);

  const targetDate = useMemo(() => {
    const date = new Date();
    date.setDate(date.getDate() - weekOffset * 7);
    return date.toISOString().split('T')[0];
  }, [weekOffset]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getWeeklySummary(targetDate);
        setData(res);
      } catch (error: unknown) {
        setError(error instanceof Error ? error.message : 'Failed to load weekly summary');
      } finally {
        setLoading(false);
      }
    })();
  }, [targetDate]);

  const weekLabel = useMemo(() => {
    if (!data) return '';
    return getWeekLabel(data.week_start);
  }, [data]);

  const comparisonColor = useMemo(() => {
    if (!data) return 'neutral';
    const change = data.comparison.change_pct;
    if (change > 10) return 'negative';
    if (change < -10) return 'positive';
    return 'neutral';
  }, [data]);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Weekly Digest</h1>
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Weekly Digest</h1>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-destructive">
          {error}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Weekly Digest</h1>
        <p className="text-muted-foreground">No data available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Weekly Digest</h1>
          <p className="text-muted-foreground">Your financial summary for {weekLabel}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => setWeekOffset((o) => o + 1)}
            disabled={weekOffset >= 4}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setWeekOffset((o) => Math.max(0, o - 1))}
            disabled={weekOffset === 0}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <FinancialCardTitle className="text-sm font-medium">
              Total Spent
            </FinancialCardTitle>
            <TrendingDown className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{currency(data.total_spent)}</div>
            <FinancialCardDescription>
              {data.comparison.change_pct > 0 ? (
                <span className="flex items-center text-red-500">
                  <ArrowUpRight className="mr-1 h-3 w-3" />
                  {data.comparison.change_pct.toFixed(1)}% vs last week
                </span>
              ) : data.comparison.change_pct < 0 ? (
                <span className="flex items-center text-green-500">
                  <ArrowDownRight className="mr-1 h-3 w-3" />
                  {Math.abs(data.comparison.change_pct).toFixed(1)}% vs last week
                </span>
              ) : (
                <span>Same as last week</span>
              )}
            </FinancialCardDescription>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <FinancialCardTitle className="text-sm font-medium">
              Total Income
            </FinancialCardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{currency(data.total_income)}</div>
            <FinancialCardDescription>
              Income this week
            </FinancialCardDescription>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <FinancialCardTitle className="text-sm font-medium">
              Net Flow
            </FinancialCardTitle>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className={cn(
              "text-2xl font-bold",
              data.net_flow >= 0 ? "text-green-600" : "text-red-600"
            )}>
              {currency(data.net_flow)}
            </div>
            <FinancialCardDescription>
              {data.net_flow >= 0 ? 'You saved this week!' : 'Spending exceeded income'}
            </FinancialCardDescription>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Insights */}
      {data.insights.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <div className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5 text-yellow-500" />
              <FinancialCardTitle>Weekly Insights</FinancialCardTitle>
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <ul className="space-y-2">
              {data.insights.map((insight, index) => (
                <li key={index} className="flex items-start gap-2 text-sm">
                  <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Category Breakdown */}
      {data.category_breakdown.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <div className="flex items-center gap-2">
              <PieChart className="h-5 w-5 text-muted-foreground" />
              <FinancialCardTitle>Spending by Category</FinancialCardTitle>
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-3">
              {data.category_breakdown.map((cat) => (
                <div key={cat.category_id ?? 'uncategorized'} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Badge variant="secondary">{cat.percentage}%</Badge>
                    <span className="text-sm font-medium">{cat.category_name}</span>
                  </div>
                  <span className="text-sm font-semibold">{currency(cat.amount)}</span>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Top Expenses */}
      {data.top_expenses.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <div className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-muted-foreground" />
              <FinancialCardTitle>Top Expenses</FinancialCardTitle>
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-3">
              {data.top_expenses.map((expense) => (
                <div key={expense.id} className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{expense.description}</p>
                    <p className="text-xs text-muted-foreground">{expense.category_name} • {formatDate(expense.date)}</p>
                  </div>
                  <span className="text-sm font-semibold text-red-600">{currency(expense.amount)}</span>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {data.total_spent === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <p className="text-muted-foreground">No expenses recorded this week.</p>
          <p className="text-sm text-muted-foreground mt-1">
            Start tracking your expenses to see your weekly digest!
          </p>
        </div>
      )}
    </div>
  );
}
