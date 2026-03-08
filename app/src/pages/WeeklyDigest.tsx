import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
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
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  Receipt,
  BarChart3,
} from 'lucide-react';
import { getWeeklySummary, type WeeklySummary } from '@/api/weekly-summary';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function formatDate(iso: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

function weekLabel(start: string, end: string) {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

export default function WeeklyDigest() {
  const [data, setData] = useState<WeeklySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [weekOffset, setWeekOffset] = useState(0);

  const weekOfDate = (() => {
    const d = new Date();
    d.setDate(d.getDate() + weekOffset * 7);
    return d.toISOString().slice(0, 10);
  })();

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        setData(await getWeeklySummary(weekOfDate));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load digest');
      } finally {
        setLoading(false);
      }
    })();
  }, [weekOfDate]);

  const totals = data?.totals ?? { income: 0, expenses: 0, net: 0, transaction_count: 0 };
  const trends = data?.trends;

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="page-header">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title flex items-center gap-2">
              <CalendarDays className="w-6 h-6" />
              Weekly Digest
            </h1>
            <p className="page-subtitle">
              {data ? weekLabel(data.week.start, data.week.end) : 'Loading…'}
            </p>
          </div>
          <div className="flex gap-2 items-center">
            <Button variant="outline" size="icon" onClick={() => setWeekOffset((o) => o - 1)}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setWeekOffset(0)}
              disabled={weekOffset === 0}
            >
              This Week
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setWeekOffset((o) => o + 1)}
              disabled={weekOffset >= 0}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
        {[
          {
            title: 'Weekly Income',
            amount: totals.income,
            icon: TrendingUp,
            trend: 'up' as const,
            change: trends?.income_change_pct,
          },
          {
            title: 'Weekly Expenses',
            amount: totals.expenses,
            icon: TrendingDown,
            trend: 'down' as const,
            change: trends?.expense_change_pct,
          },
          {
            title: 'Net Flow',
            amount: totals.net,
            icon: Wallet,
            trend: totals.net >= 0 ? ('up' as const) : ('down' as const),
            change: null,
          },
          {
            title: 'Transactions',
            amount: totals.transaction_count,
            icon: Receipt,
            trend: 'up' as const,
            change: null,
            raw: true,
          },
        ].map((card, i) => (
          <FinancialCard key={i} variant="financial" className="group card-interactive fade-in-up">
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
                {loading ? '...' : 'raw' in card ? card.amount : currency(card.amount)}
              </div>
              {card.change !== null && card.change !== undefined && (
                <div className="flex items-center text-sm">
                  {card.change >= 0 ? (
                    <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                  ) : (
                    <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                  )}
                  <span
                    className={
                      card.change >= 0
                        ? 'text-success font-medium'
                        : 'text-destructive font-medium'
                    }
                  >
                    {card.change > 0 ? '+' : ''}
                    {card.change.toFixed(1)}% vs last week
                  </span>
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Daily spending chart (simple bar) */}
        <div className="lg:col-span-2">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title flex items-center gap-2">
                <BarChart3 className="w-5 h-5" />
                Daily Spending
              </FinancialCardTitle>
              <FinancialCardDescription>Expenses by day of the week</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.daily_breakdown && data.daily_breakdown.length > 0 ? (
                <div className="space-y-2">
                  {data.daily_breakdown.map((day) => {
                    const maxExpense = Math.max(
                      ...data.daily_breakdown.map((d) => d.expenses),
                      1,
                    );
                    const pct = Math.max(2, (day.expenses / maxExpense) * 100);
                    return (
                      <div key={day.date} className="flex items-center gap-3">
                        <span className="w-20 text-sm text-muted-foreground shrink-0">
                          {formatDate(day.date)}
                        </span>
                        <div className="flex-1 chart-track h-6 relative">
                          <div
                            className="chart-fill-primary h-6 rounded-r-md"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="w-24 text-sm font-medium text-right">
                          {currency(day.expenses)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No spending data this week.</p>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Top expenses */}
          <FinancialCard variant="financial" className="fade-in-up mt-6">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Top Expenses</FinancialCardTitle>
              <FinancialCardDescription>Biggest purchases this week</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.top_expenses && data.top_expenses.length > 0 ? (
                <div className="space-y-3">
                  {data.top_expenses.map((e) => (
                    <div key={e.id} className="interactive-row flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-destructive-light text-destructive">
                          <ArrowDownRight className="w-5 h-5" />
                        </div>
                        <div>
                          <div className="font-medium text-foreground">{e.description}</div>
                          <div className="text-sm text-muted-foreground">{formatDate(e.date)}</div>
                        </div>
                      </div>
                      <div className="font-semibold text-foreground">
                        -{currency(e.amount, e.currency)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No expenses this week.</p>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>

        {/* Right column: categories + bills */}
        <div className="space-y-6">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Category Breakdown</FinancialCardTitle>
              <FinancialCardDescription>Where your money went</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.category_breakdown && data.category_breakdown.length > 0 ? (
                <div className="space-y-3">
                  {data.category_breakdown.map((row) => (
                    <div
                      key={`${row.category_id ?? 'uncat'}-${row.category_name}`}
                      className="space-y-1"
                    >
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-foreground">{row.category_name}</span>
                        <span className="text-muted-foreground">
                          {currency(row.amount)} ({row.share_pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="chart-track h-2">
                        <div
                          className="chart-fill-primary h-2"
                          style={{
                            width: `${Math.max(2, Math.min(100, row.share_pct))}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No category data.</p>
              )}
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Upcoming Bills</FinancialCardTitle>
              <FinancialCardDescription>Bills due this & next week</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data?.upcoming_bills && data.upcoming_bills.length > 0 ? (
                <div className="space-y-3">
                  {data.upcoming_bills.map((bill) => (
                    <div key={bill.id} className="interactive-row flex items-center justify-between">
                      <div>
                        <div className="font-medium text-foreground text-sm">{bill.name}</div>
                        <div className="text-xs text-muted-foreground">
                          Due {formatDate(bill.next_due_date)}
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-foreground">
                        {currency(bill.amount, bill.currency)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No bills due soon.</p>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      </div>
    </div>
  );
}
