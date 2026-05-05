import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ArrowDownRight,
  ArrowUpRight,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  Minus,
  Calendar,
  CreditCard,
} from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigestResponse } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function formatDateRange(start: string, end: string): string {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  return `${startDate.toLocaleDateString('en-US', options)} - ${endDate.toLocaleDateString('en-US', options)}`;
}

function TrendBadge({ trend, delta }: { trend: string; delta: number | null }) {
  if (trend === 'up') {
    return (
      <span className="inline-flex items-center text-xs font-medium text-destructive">
        <ArrowUpRight className="w-3 h-3 mr-1" />
        {delta !== null ? `${Math.abs(delta).toFixed(1)}%` : ''}
      </span>
    );
  }
  if (trend === 'down') {
    return (
      <span className="inline-flex items-center text-xs font-medium text-success">
        <ArrowDownRight className="w-3 h-3 mr-1" />
        {delta !== null ? `${Math.abs(delta).toFixed(1)}%` : ''}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center text-xs font-medium text-muted-foreground">
      <Minus className="w-3 h-3 mr-1" />
      0%
    </span>
  );
}

export function Digest() {
  const [data, setData] = useState<WeeklyDigestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [weeks, setWeeks] = useState(4);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getWeeklyDigest(weeks);
        setData(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load digest');
      } finally {
        setLoading(false);
      }
    })();
  }, [weeks]);

  if (loading) {
    return (
      <div className="page-wrap">
        <div className="page-header">
          <h1 className="page-title">Weekly Spending Digest</h1>
          <p className="page-subtitle">Analyzing your weekly spending patterns...</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
          {[1, 2, 3, 4].map((i) => (
            <FinancialCard key={i} variant="financial" className="animate-pulse">
              <FinancialCardHeader className="pb-3">
                <div className="h-4 bg-muted rounded w-24"></div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="h-8 bg-muted rounded w-32 mb-2"></div>
                <div className="h-4 bg-muted rounded w-20"></div>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-wrap">
        <div className="page-header">
          <h1 className="page-title">Weekly Spending Digest</h1>
          <p className="page-subtitle">Analyzing your weekly spending patterns...</p>
        </div>
        <div className="error">{error}</div>
      </div>
    );
  }

  const currentWeek = data?.weeks?.[0];
  const previousWeek = data?.weeks?.[1];

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Weekly Spending Digest</h1>
            <p className="page-subtitle">
              Week-over-week analysis for {data?.period?.weeks} weeks
            </p>
          </div>
          <Tabs value={String(weeks)} onValueChange={(v) => setWeeks(Number(v))}>
            <TabsList>
              <TabsTrigger value="4">4w</TabsTrigger>
              <TabsTrigger value="8">8w</TabsTrigger>
              <TabsTrigger value="12">12w</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-3">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
              Current Week Total
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {currency(currentWeek?.total || 0)}
            </div>
            <div className="flex items-center text-sm">
              {currentWeek && (
                <TrendBadge trend={currentWeek.trend} delta={currentWeek.delta_percent} />
              )}
              <span className="text-muted-foreground ml-2">vs last week</span>
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-3">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
              Previous Week Total
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {currency(previousWeek?.total || 0)}
            </div>
            <div className="text-sm text-muted-foreground">
              {previousWeek ? formatDateRange(previousWeek.week_start, previousWeek.week_end) : 'No data'}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-3">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
              Top Category
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {data?.top_categories?.[0]?.category_name || 'N/A'}
            </div>
            <div className="text-sm text-muted-foreground">
              {currency(data?.top_categories?.[0]?.amount || 0)}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-3">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
              Upcoming Bills
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {data?.upcoming_bills?.length || 0}
            </div>
            <div className="text-sm text-muted-foreground">
              Next 7 days
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Weekly Cards */}
        <div className="lg:col-span-2">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Weekly Breakdown</FinancialCardTitle>
              <FinancialCardDescription>
                Spending by week with trend analysis
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.weeks?.length === 0 ? (
                <div className="text-sm text-muted-foreground">No expense data for this period.</div>
              ) : (
                <div className="space-y-4">
                  {data?.weeks?.map((week, index) => (
                    <div
                      key={week.week_start}
                      className={`interactive-row p-4 rounded-lg border border-border ${
                        index === 0 ? 'bg-primary/5 border-primary/20' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-muted-foreground" />
                          <span className="font-medium text-foreground">
                            {formatDateRange(week.week_start, week.week_end)}
                          </span>
                          {index === 0 && (
                            <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded">
                              Current
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-semibold text-foreground">
                            {currency(week.total)}
                          </span>
                          <TrendBadge trend={week.trend} delta={week.delta_percent} />
                        </div>
                      </div>
                      {week.categories.length > 0 && (
                        <div className="space-y-2">
                          {week.categories.map((cat) => (
                            <div key={cat.category_id} className="flex items-center justify-between text-sm">
                              <span className="text-muted-foreground">{cat.category_name}</span>
                              <span className="text-foreground">{currency(cat.amount)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Top Categories */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Top Categories</FinancialCardTitle>
              <FinancialCardDescription>
                Highest spending categories
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.top_categories?.length === 0 ? (
                <div className="text-sm text-muted-foreground">No categories found.</div>
              ) : (
                <div className="space-y-3">
                  {data?.top_categories?.map((cat, index) => (
                    <div key={cat.category_id} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
                          {index + 1}
                        </span>
                        <span className="text-sm text-foreground">{cat.category_name}</span>
                      </div>
                      <span className="text-sm font-medium text-foreground">{currency(cat.amount)}</span>
                    </div>
                  ))}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Upcoming Bills */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Upcoming Bills</FinancialCardTitle>
              <FinancialCardDescription>
                Due in the next 7 days
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.upcoming_bills?.length === 0 ? (
                <div className="text-sm text-muted-foreground">No upcoming bills.</div>
              ) : (
                <div className="space-y-3">
                  {data?.upcoming_bills?.map((bill) => (
                    <div key={bill.id} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CreditCard className="w-4 h-4 text-muted-foreground" />
                        <div>
                          <div className="text-sm text-foreground">{bill.name}</div>
                          <div className="text-xs text-muted-foreground">
                            Due {new Date(bill.next_due_date).toLocaleDateString()}
                          </div>
                        </div>
                      </div>
                      <span className="text-sm font-medium text-foreground">
                        {currency(bill.amount, bill.currency)}
                      </span>
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