import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import {
  getWeeklyDigest,
  currentISOWeek,
  type WeeklyDigest,
} from '@/api/digest';
import { formatMoney } from '@/lib/currency';
import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Lightbulb,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from 'lucide-react';

function parseWeek(w: string): { year: number; week: number } {
  const [y, wPart] = w.split('-W');
  return { year: parseInt(y, 10), week: parseInt(wPart, 10) };
}

function shiftWeek(w: string, delta: number): string {
  const { year, week } = parseWeek(w);
  // Simple approximation: shift by 7 days
  const jan4 = new Date(year, 0, 4);
  const dow = jan4.getDay() === 0 ? 7 : jan4.getDay();
  const startOfWeek1 = new Date(jan4.getTime() - (dow - 1) * 86400000);
  const targetMonday = new Date(startOfWeek1.getTime() + (week - 1 + delta) * 7 * 86400000);
  // Get ISO week of target
  const y = targetMonday.getFullYear();
  const jan4New = new Date(y, 0, 4);
  const dowNew = jan4New.getDay() === 0 ? 7 : jan4New.getDay();
  const startNew = new Date(jan4New.getTime() - (dowNew - 1) * 86400000);
  const diff = Math.floor((targetMonday.getTime() - startNew.getTime()) / (7 * 86400000)) + 1;
  return `${y}-W${String(diff).padStart(2, '0')}`;
}

export function Digest() {
  const { toast } = useToast();
  const [week, setWeek] = useState(currentISOWeek);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<WeeklyDigest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [geminiKey, setGeminiKey] = useState('');

  async function load(targetWeek?: string) {
    const w = targetWeek || week;
    setLoading(true);
    setError(null);
    try {
      const payload = await getWeeklyDigest({
        week: w,
        geminiApiKey: geminiKey.trim() || undefined,
      });
      setData(payload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load digest';
      setError(message);
      toast({ title: 'Failed to load digest', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handlePrev() {
    const prev = shiftWeek(week, -1);
    setWeek(prev);
    void load(prev);
  }

  function handleNext() {
    const next = shiftWeek(week, 1);
    setWeek(next);
    void load(next);
  }

  const trendIcon = useMemo(() => {
    if (!data) return null;
    const pct = data.trends.expense_change_pct;
    if (pct > 0) return <TrendingUp className="w-4 h-4 text-destructive" />;
    if (pct < 0) return <TrendingDown className="w-4 h-4 text-success" />;
    return null;
  }, [data]);

  return (
    <div className="page-wrap space-y-6">
      {/* Header */}
      <div className="page-header">
        <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              Your financial week at a glance — trends, insights, and actionable tips.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={handlePrev} aria-label="Previous week">
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm font-semibold min-w-[90px] text-center">{week}</span>
            <Button variant="outline" size="icon" onClick={handleNext} aria-label="Next week">
              <ChevronRight className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => { const cw = currentISOWeek(); setWeek(cw); void load(cw); }}>
              <CalendarDays className="w-4 h-4 mr-1" /> This Week
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <div>
              <Label htmlFor="digest-gemini-key" className="text-xs">Gemini Key (optional)</Label>
              <Input
                id="digest-gemini-key"
                type="password"
                className="h-8 w-[180px]"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIza..."
              />
            </div>
            <Button onClick={() => load()} disabled={loading} size="sm" className="mt-5">
              Refresh
            </Button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="card">Loading weekly digest...</div>
      ) : error ? (
        <div className="card text-red-600">{error}</div>
      ) : data ? (
        <div className="space-y-6">
          {/* Period */}
          <div className="text-sm text-muted-foreground">
            {new Date(data.period.start).toLocaleDateString()} — {new Date(data.period.end).toLocaleDateString()}
            <span className="ml-2 text-xs opacity-70">({data.summary.transaction_count} transactions)</span>
          </div>

          {/* Summary cards */}
          <div className="grid gap-4 md:grid-cols-4">
            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm">Net Flow</FinancialCardTitle>
                  <Wallet className="w-5 h-5 text-muted-foreground" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className={`metric-value ${data.summary.net_flow >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {data.summary.net_flow >= 0 ? '+' : ''}{formatMoney(data.summary.net_flow)}
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm">Income</FinancialCardTitle>
                  <ArrowUpRight className="w-5 h-5 text-success" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value text-success">{formatMoney(data.summary.total_income)}</div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm">Expenses</FinancialCardTitle>
                  <ArrowDownRight className="w-5 h-5 text-destructive" />
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value">{formatMoney(data.summary.total_expenses)}</div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="group card-interactive fade-in-up">
              <FinancialCardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm">WoW Spending</FinancialCardTitle>
                  {trendIcon}
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="metric-value">
                  {data.trends.expense_change_pct >= 0 ? '+' : ''}
                  {data.trends.expense_change_pct.toFixed(1)}%
                </div>
                <div className="text-xs text-muted-foreground">vs {data.trends.previous_week}</div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* Insights */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center gap-2">
                <Lightbulb className="w-5 h-5 text-primary" />
                <FinancialCardTitle>Weekly Insights</FinancialCardTitle>
              </div>
              <FinancialCardDescription>
                {data.method === 'gemini' ? 'AI-powered analysis' : 'Heuristic analysis'}
                {data.warnings?.length ? ` (${data.warnings.join(', ')})` : ''}
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data.insights.length > 0 ? (
                <ul className="space-y-2">
                  {data.insights.map((insight, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <Zap className="w-4 h-4 mt-0.5 text-primary flex-shrink-0" />
                      <span className="text-sm">{insight}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No insights available for this week.</p>
              )}
            </FinancialCardContent>
          </FinancialCard>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Daily Spending */}
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">Daily Spending</FinancialCardTitle>
                <FinancialCardDescription>Expense breakdown by day</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                {data.daily_spending.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No spending this week.</p>
                ) : (
                  <div className="space-y-2">
                    {data.daily_spending.map((day) => {
                      const maxAmount = Math.max(...data.daily_spending.map(d => d.amount));
                      const pct = maxAmount > 0 ? (day.amount / maxAmount) * 100 : 0;
                      return (
                        <div key={day.date} className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-foreground">
                              {new Date(day.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                            </span>
                            <span className="text-muted-foreground font-medium">{formatMoney(day.amount)}</span>
                          </div>
                          <div className="chart-track h-2">
                            <div
                              className="chart-fill-primary h-2"
                              style={{ width: `${Math.max(2, pct)}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>

            {/* Category Breakdown */}
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">Category Breakdown</FinancialCardTitle>
                <FinancialCardDescription>Where your money went</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                {data.category_breakdown.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No categorised expenses.</p>
                ) : (
                  <div className="space-y-3">
                    {data.category_breakdown.slice(0, 8).map((row) => (
                      <div key={`${row.category_id ?? 'uncat'}-${row.category_name}`} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-foreground">{row.category_name}</span>
                          <span className="text-muted-foreground">
                            {formatMoney(row.amount)} ({row.share_pct.toFixed(0)}%)
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
          </div>

          {/* Transactions */}
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="section-title">Transactions This Week</FinancialCardTitle>
              <FinancialCardDescription>{data.transactions.length} transaction(s)</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data.transactions.length === 0 ? (
                <p className="text-sm text-muted-foreground">No transactions this week.</p>
              ) : (
                <div className="space-y-3">
                  {data.transactions.map((tx) => {
                    const isIncome = tx.type === 'INCOME';
                    return (
                      <div key={tx.id} className="interactive-row flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                            isIncome ? 'bg-success-light text-success' : 'bg-destructive-light text-destructive'
                          }`}>
                            {isIncome ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
                          </div>
                          <div>
                            <div className="font-medium text-foreground text-sm">{tx.description}</div>
                            <div className="text-xs text-muted-foreground">{new Date(tx.date).toLocaleDateString()}</div>
                          </div>
                        </div>
                        <div className={`text-sm font-semibold ${isIncome ? 'text-success' : 'text-foreground'}`}>
                          {isIncome ? '+' : '-'}{formatMoney(Math.abs(tx.amount), tx.currency)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          {/* Upcoming Bills */}
          {data.upcoming_bills.length > 0 && (
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">Bills Due This Week</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-2">
                  {data.upcoming_bills.map((bill) => (
                    <div key={bill.id} className="flex items-center justify-between text-sm">
                      <span className="text-foreground">{bill.name}</span>
                      <span className="font-semibold">{formatMoney(bill.amount, bill.currency)}</span>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}
        </div>
      ) : null}
    </div>
  );
}
