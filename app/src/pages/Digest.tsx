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
  Calendar,
  ChevronLeft,
  ChevronRight,
  Lightbulb,
  TrendingDown,
  TrendingUp,
  Wallet,
  BarChart3,
} from 'lucide-react';
import {
  getWeeklyDigest,
  getAvailableWeeks,
  type WeeklyDigest,
  type DigestWeek,
} from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + 'T00:00:00');
  const e = new Date(end + 'T00:00:00');
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  return `${s.toLocaleDateString(undefined, opts)} – ${e.toLocaleDateString(undefined, { ...opts, year: 'numeric' })}`;
}

function dayLabel(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short' });
}

export default function Digest() {
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [weeks, setWeeks] = useState<DigestWeek[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const available = await getAvailableWeeks(24);
        setWeeks(available);
      } catch {
        // Non-critical — week picker just won't show
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const weekStart = weeks.length > 0 ? weeks[selectedIdx]?.week_start : undefined;
        const res = await getWeeklyDigest(weekStart);
        setDigest(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load digest');
      } finally {
        setLoading(false);
      }
    })();
  }, [weeks, selectedIdx]);

  const canGoNewer = selectedIdx > 0;
  const canGoOlder = selectedIdx < weeks.length - 1;

  const summary = digest?.summary;
  const comparison = digest?.comparison;
  const wowPct = comparison?.week_over_week_change_pct ?? 0;
  const wowUp = wowPct > 0;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              {digest
                ? formatDateRange(digest.period.week_start, digest.period.week_end)
                : 'Your weekly financial summary'}
            </p>
          </div>
          {weeks.length > 0 && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                disabled={!canGoOlder}
                onClick={() => setSelectedIdx((i) => i + 1)}
                aria-label="Older week"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <div className="flex items-center gap-1.5 rounded-full border border-border/70 bg-white/70 px-3 py-1.5 text-xs font-medium">
                <Calendar className="w-3.5 h-3.5 text-primary" />
                {digest
                  ? formatDateRange(digest.period.week_start, digest.period.week_end)
                  : 'Loading...'}
              </div>
              <Button
                variant="outline"
                size="icon"
                disabled={!canGoNewer}
                onClick={() => setSelectedIdx((i) => i - 1)}
                aria-label="Newer week"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="error mb-6">{error}</div>
      )}

      {loading && !digest && (
        <div className="text-center py-12 text-muted-foreground">Loading digest...</div>
      )}

      {digest && (
        <>
          {/* Summary cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Net Flow</FinancialCardTitle>
                  <Wallet className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {currency(summary?.net_flow ?? 0)}
                </div>
                <div className="flex items-center text-sm">
                  {(summary?.net_flow ?? 0) >= 0 ? (
                    <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                  ) : (
                    <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                  )}
                  <span className="text-muted-foreground">This week</span>
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Income</FinancialCardTitle>
                  <TrendingUp className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {currency(summary?.total_income ?? 0)}
                </div>
                <div className="text-sm text-muted-foreground">
                  {summary?.transaction_count ?? 0} transactions
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Expenses</FinancialCardTitle>
                  <TrendingDown className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {currency(summary?.total_expenses ?? 0)}
                </div>
                <div className="flex items-center text-sm">
                  {wowUp ? (
                    <ArrowUpRight className="w-4 h-4 text-destructive mr-1" />
                  ) : (
                    <ArrowDownRight className="w-4 h-4 text-success mr-1" />
                  )}
                  <span className={wowUp ? 'text-destructive font-medium mr-1' : 'text-success font-medium mr-1'}>
                    {wowPct > 0 ? '+' : ''}{wowPct.toFixed(1)}%
                  </span>
                  <span className="text-muted-foreground">vs last week</span>
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Prev Week</FinancialCardTitle>
                  <BarChart3 className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-foreground mb-1">
                  {currency(comparison?.prev_week_expenses ?? 0)}
                </div>
                <div className="text-sm text-muted-foreground">Previous week expenses</div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          <div className="grid lg:grid-cols-3 gap-8">
            {/* Left column: Daily chart + Top transactions */}
            <div className="lg:col-span-2 space-y-6">
              {/* Daily spending bar chart */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">Daily Spending</FinancialCardTitle>
                  <FinancialCardDescription>Day-by-day expense breakdown</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {digest.daily_spending.length > 0 ? (
                    <div className="flex items-end gap-2 h-40">
                      {(() => {
                        const maxAmt = Math.max(...digest.daily_spending.map((d) => d.amount), 1);
                        return digest.daily_spending.map((day) => (
                          <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
                            <span className="text-[10px] text-muted-foreground font-medium">
                              {day.amount > 0 ? currency(day.amount) : ''}
                            </span>
                            <div
                              className="w-full rounded-t-md bg-primary/80 hover:bg-primary transition-colors min-h-[4px]"
                              style={{ height: `${Math.max((day.amount / maxAmt) * 100, 3)}%` }}
                            />
                            <span className="text-[11px] text-muted-foreground">{dayLabel(day.date)}</span>
                          </div>
                        ));
                      })()}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">No spending data.</div>
                  )}
                </FinancialCardContent>
              </FinancialCard>

              {/* Top transactions */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">Top Transactions</FinancialCardTitle>
                  <FinancialCardDescription>Largest expenses this week</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {digest.top_transactions.length === 0 ? (
                    <div className="text-sm text-muted-foreground">No transactions this week.</div>
                  ) : (
                    <div className="space-y-3">
                      {digest.top_transactions.map((txn) => (
                        <div key={txn.id} className="interactive-row flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-destructive-light text-destructive">
                              <ArrowDownRight className="w-5 h-5" />
                            </div>
                            <div>
                              <div className="font-medium text-foreground">{txn.description}</div>
                              <div className="text-sm text-muted-foreground">
                                {new Date(txn.date + 'T00:00:00').toLocaleDateString()}
                              </div>
                            </div>
                          </div>
                          <div className="font-semibold text-foreground">
                            -{currency(txn.amount)}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            </div>

            {/* Right column: Categories + Insights */}
            <div className="space-y-6">
              {/* Category breakdown */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <FinancialCardTitle className="section-title">Category Breakdown</FinancialCardTitle>
                  <FinancialCardDescription>Where your money went</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {digest.category_breakdown.length === 0 ? (
                    <div className="text-sm text-muted-foreground">No category data this week.</div>
                  ) : (
                    <div className="space-y-3">
                      {digest.category_breakdown.slice(0, 8).map((row) => (
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

              {/* Insights */}
              <FinancialCard variant="financial" className="fade-in-up">
                <FinancialCardHeader>
                  <div className="flex items-center gap-2">
                    <Lightbulb className="w-5 h-5 text-primary" />
                    <FinancialCardTitle className="section-title">Insights</FinancialCardTitle>
                  </div>
                  <FinancialCardDescription>AI-powered observations</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  {digest.insights.length === 0 ? (
                    <div className="text-sm text-muted-foreground">
                      Add more transactions to unlock insights.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {digest.insights.map((insight, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-3 rounded-lg border border-border/60 bg-muted/30 p-3"
                        >
                          <div className="mt-0.5 w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                            <span className="text-[10px] font-bold text-primary">{i + 1}</span>
                          </div>
                          <p className="text-sm text-foreground leading-relaxed">{insight}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            </div>
          </div>
        </>
      )}

      {!loading && !digest && !error && (
        <div className="text-center py-16">
          <BarChart3 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-foreground mb-2">No digest available</h2>
          <p className="text-muted-foreground">
            Start tracking expenses to see your weekly financial summary here.
          </p>
        </div>
      )}
    </div>
  );
}
