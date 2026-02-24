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
  Calendar,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Lightbulb,
  Trophy,
  ChevronLeft,
  ChevronRight,
  BarChart3,
} from 'lucide-react';
import { getWeeklySummary, type WeeklySummary, type WeeklyInsight } from '@/api/weekly-summary';
import { formatMoney } from '@/lib/currency';
import { format, startOfWeek, endOfWeek, subWeeks, addWeeks } from 'date-fns';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function getInsightIcon(type: WeeklyInsight['type']) {
  switch (type) {
    case 'trend':
      return <TrendingUp className="w-4 h-4" />;
    case 'alert':
      return <AlertCircle className="w-4 h-4" />;
    case 'tip':
      return <Lightbulb className="w-4 h-4" />;
    case 'achievement':
      return <Trophy className="w-4 h-4" />;
  }
}

function getInsightColor(severity: WeeklyInsight['severity']) {
  switch (severity) {
    case 'positive':
      return 'bg-success-light text-success border-success/20';
    case 'negative':
      return 'bg-destructive-light text-destructive border-destructive/20';
    default:
      return 'bg-muted text-muted-foreground border-muted';
  }
}

export function WeeklyDigest() {
  const [data, setData] = useState<WeeklySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [weekOffset, setWeekOffset] = useState(0);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getWeeklySummary(weekOffset);
        setData(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load weekly summary');
      } finally {
        setLoading(false);
      }
    })();
  }, [weekOffset]);

  const weekLabel = useMemo(() => {
    if (!data) return '';
    const start = new Date(data.week_start);
    const end = new Date(data.week_end);
    return `${format(start, 'MMM d')} - ${format(end, 'MMM d, yyyy')}`;
  }, [data]);

  const handlePreviousWeek = () => setWeekOffset((prev) => prev - 1);
  const handleNextWeek = () => setWeekOffset((prev) => (prev < 0 ? prev + 1 : prev));

  const isCurrentWeek = weekOffset === 0;

  return (
    <FinancialCard variant="financial" className="fade-in-up">
      <FinancialCardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <FinancialCardTitle className="section-title">Weekly Digest</FinancialCardTitle>
            <Badge variant={isCurrentWeek ? 'default' : 'secondary'} className="text-xs">
              {isCurrentWeek ? 'This Week' : 'Past Week'}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={handlePreviousWeek}
              className="h-8 w-8"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <div className="flex items-center gap-1 text-sm text-muted-foreground min-w-[180px] justify-center">
              <Calendar className="w-4 h-4" />
              {loading ? '...' : weekLabel}
            </div>
            <Button
              variant="outline"
              size="icon"
              onClick={handleNextWeek}
              disabled={weekOffset >= 0}
              className="h-8 w-8"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
        <FinancialCardDescription>
          AI-powered insights and trends for your weekly finances
        </FinancialCardDescription>
      </FinancialCardHeader>

      <FinancialCardContent className="space-y-6">
        {error && (
          <div className="text-sm text-destructive bg-destructive-light p-3 rounded-md">
            {error}
          </div>
        )}

        {/* Summary Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Net Flow</p>
            <p className={`text-lg font-semibold ${
              (data?.net_flow || 0) >= 0 ? 'text-success' : 'text-destructive'
            }`}>
              {loading ? '...' : currency(data?.net_flow || 0)}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Income</p>
            <p className="text-lg font-semibold text-success">
              {loading ? '...' : currency(data?.total_income || 0)}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Expenses</p>
            <p className="text-lg font-semibold text-destructive">
              {loading ? '...' : currency(data?.total_expenses || 0)}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Transactions</p>
            <p className="text-lg font-semibold">
              {loading ? '...' : data?.transaction_count || 0}
            </p>
          </div>
        </div>

        {/* Week-over-week comparison */}
        {!loading && data && (
          <div className="flex flex-wrap gap-3">
            <Badge 
              variant="outline" 
              className={`text-xs ${
                data.comparison_to_last_week.expense_change_pct <= 0 
                  ? 'text-success border-success/30' 
                  : 'text-destructive border-destructive/30'
              }`}
            >
              {data.comparison_to_last_week.expense_change_pct <= 0 ? (
                <TrendingDown className="w-3 h-3 mr-1" />
              ) : (
                <TrendingUp className="w-3 h-3 mr-1" />
              )}
              Expenses {Math.abs(data.comparison_to_last_week.expense_change_pct).toFixed(1)}% vs last week
            </Badge>
            {data.comparison_to_last_week.income_change_pct !== 0 && (
              <Badge 
                variant="outline" 
                className={`text-xs ${
                  data.comparison_to_last_week.income_change_pct >= 0 
                    ? 'text-success border-success/30' 
                    : 'text-destructive border-destructive/30'
                }`}
              >
                {data.comparison_to_last_week.income_change_pct >= 0 ? (
                  <TrendingUp className="w-3 h-3 mr-1" />
                ) : (
                  <TrendingDown className="w-3 h-3 mr-1" />
                )}
                Income {Math.abs(data.comparison_to_last_week.income_change_pct).toFixed(1)}% vs last week
              </Badge>
            )}
            {data.top_expense_category && (
              <Badge variant="outline" className="text-xs text-muted-foreground">
                <BarChart3 className="w-3 h-3 mr-1" />
                Top: {data.top_expense_category.name} ({data.top_expense_category.percentage.toFixed(0)}%)
              </Badge>
            )}
          </div>
        )}

        {/* Insights */}
        {!loading && data?.insights && data.insights.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-sm font-medium">Insights</h4>
            <div className="space-y-2">
              {data.insights.map((insight, index) => (
                <div
                  key={index}
                  className={`flex items-start gap-3 p-3 rounded-md border ${getInsightColor(insight.severity)}`}
                >
                  <div className="mt-0.5 shrink-0">{getInsightIcon(insight.type)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{insight.title}</p>
                    <p className="text-xs opacity-90 mt-0.5">{insight.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && data?.transaction_count === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <Calendar className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No transactions this week</p>
            <p className="text-xs mt-1">Add expenses to see your weekly digest</p>
          </div>
        )}
      </FinancialCardContent>
    </FinancialCard>
  );
}
