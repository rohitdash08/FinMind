import { useEffect, useState } from 'react';
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
import { getWeeklyDigest, getDigestHistory, type WeeklyDigest } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function currentISOWeek(): string {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const daysSinceJan4 = Math.floor((now.getTime() - jan4.getTime()) / 86400000);
  const weekNum = Math.ceil((daysSinceJan4 + jan4.getDay() + 1) / 7);
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

export function Digest() {
  const { toast } = useToast();
  const [week, setWeek] = useState(currentISOWeek);
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [history, setHistory] = useState<WeeklyDigest[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [d, h] = await Promise.all([
        getWeeklyDigest(week),
        getDigestHistory(4),
      ]);
      setDigest(d);
      setHistory(h);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load digest';
      toast({ title: 'Error', description: msg });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [week]);

  const wowColor =
    digest && digest.week_over_week_change_pct > 0
      ? 'text-destructive'
      : digest && digest.week_over_week_change_pct < 0
        ? 'text-green-600'
        : '';

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              Your smart weekly financial summary powered by AI insights.
            </p>
          </div>
          <div className="flex gap-2 items-end">
            <div>
              <Label htmlFor="digest-week">Week</Label>
              <Input
                id="digest-week"
                type="week"
                value={week}
                onChange={(e) => setWeek(e.target.value)}
                className="w-44"
              />
            </div>
            <Button variant="hero" onClick={() => void load()} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </Button>
          </div>
        </div>
      </div>

      {digest && (
        <>
          {/* Summary cards */}
          <div className="grid gap-4 md:grid-cols-4">
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Income</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-2xl font-bold text-green-600">
                  {formatMoney(digest.summary.total_income)}
                </p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Expenses</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-2xl font-bold text-destructive">
                  {formatMoney(digest.summary.total_expenses)}
                </p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant={digest.summary.net_flow >= 0 ? 'success' : 'destructive'}>
              <FinancialCardHeader>
                <FinancialCardTitle>Net Flow</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-2xl font-bold">
                  {formatMoney(digest.summary.net_flow)}
                </p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Week-over-Week</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className={`text-2xl font-bold ${wowColor}`}>
                  {digest.week_over_week_change_pct > 0 ? '+' : ''}
                  {digest.week_over_week_change_pct.toFixed(1)}%
                </p>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* AI Narrative */}
          <FinancialCard variant="premium">
            <FinancialCardHeader>
              <FinancialCardTitle>AI Weekly Insights</FinancialCardTitle>
              <FinancialCardDescription>
                {digest.period.start} → {digest.period.end}
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-sm leading-relaxed">{digest.narrative}</p>
            </FinancialCardContent>
          </FinancialCard>

          {/* Category breakdown & Top expense */}
          <div className="grid gap-4 md:grid-cols-2">
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Category Breakdown</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {digest.category_breakdown.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No expenses this week.</p>
                ) : (
                  <div className="space-y-2">
                    {digest.category_breakdown.map((c) => (
                      <div key={c.category} className="flex justify-between text-sm">
                        <span>{c.category}</span>
                        <span className="font-medium">{formatMoney(c.amount)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Upcoming Bills</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {digest.upcoming_bills.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No bills due this week.</p>
                ) : (
                  <div className="space-y-2">
                    {digest.upcoming_bills.map((b) => (
                      <div key={b.name} className="flex justify-between text-sm">
                        <span>{b.name} <span className="text-muted-foreground">({b.due_date})</span></span>
                        <span className="font-medium">{formatMoney(b.amount)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* Top expense */}
          {digest.top_expense && (
            <FinancialCard variant="warning">
              <FinancialCardHeader>
                <FinancialCardTitle>Biggest Expense</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-lg font-bold">{formatMoney(digest.top_expense.amount)}</p>
                <p className="text-sm text-muted-foreground">
                  {digest.top_expense.notes} — {digest.top_expense.date}
                </p>
              </FinancialCardContent>
            </FinancialCard>
          )}
        </>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Recent Weeks</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {history.map((h) => (
              <FinancialCard
                key={h.week}
                className="cursor-pointer"
                onClick={() => setWeek(h.week)}
              >
                <FinancialCardHeader>
                  <FinancialCardTitle className="text-sm">{h.week}</FinancialCardTitle>
                  <FinancialCardDescription>
                    {h.period.start} → {h.period.end}
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <div className="flex justify-between text-xs">
                    <span className="text-green-600">{formatMoney(h.summary.total_income)}</span>
                    <span className="text-destructive">{formatMoney(h.summary.total_expenses)}</span>
                  </div>
                  <p className="mt-1 text-xs font-semibold">
                    Net: {formatMoney(h.summary.net_flow)}
                  </p>
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>
        </div>
      )}

      {loading && !digest && (
        <div className="flex items-center justify-center py-20">
          <p className="text-muted-foreground">Loading your weekly digest…</p>
        </div>
      )}
    </div>
  );
}
