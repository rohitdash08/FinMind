import { useState, useEffect, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import { TrendingUp, TrendingDown, Minus, CalendarDays, Lightbulb, Receipt, AlertCircle } from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigest, type CategoryBreakdown } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function WowBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-muted-foreground">No prior data</span>;
  if (Math.abs(pct) < 1) return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Minus className="w-3 h-3" /> Flat vs last week
    </span>
  );
  const up = pct > 0;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${up ? 'text-destructive' : 'text-success'}`}>
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {up ? '+' : ''}{pct.toFixed(1)}% vs last week
    </span>
  );
}

function CategoryBar({ item, max }: { item: CategoryBreakdown; max: number }) {
  const pct = max > 0 ? (item.total / max) * 100 : 0;
  const hasDelta = item.delta_pct !== null;
  const up = (item.delta ?? 0) > 0;

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center text-sm">
        <span className="font-medium">{item.category}</span>
        <div className="flex items-center gap-2">
          {hasDelta && (
            <span className={`text-xs ${up ? 'text-destructive' : 'text-success'}`}>
              {up ? '+' : ''}{item.delta_pct?.toFixed(0)}%
            </span>
          )}
          <span>{formatMoney(item.total, 'INR')}</span>
        </div>
      </div>
      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function Digest() {
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [weekOffset, setWeekOffset] = useState(0);
  const { toast } = useToast();

  const getWeekStart = useCallback((offset: number) => {
    const d = new Date();
    d.setDate(d.getDate() - d.getDay() + 1 - offset * 7); // most recent Monday - offset
    return d.toISOString().slice(0, 10);
  }, []);

  const load = useCallback(async (offset: number) => {
    try {
      setLoading(true);
      const data = await getWeeklyDigest(getWeekStart(offset));
      setDigest(data);
    } catch {
      toast({ title: 'Failed to load weekly digest', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast, getWeekStart]);

  useEffect(() => {
    load(weekOffset);
  }, [load, weekOffset]);

  const maxCategorySpend = digest
    ? Math.max(...digest.category_breakdown.map((c) => c.total), 1)
    : 1;

  const weekLabel = weekOffset === 0 ? 'This Week' : weekOffset === 1 ? 'Last Week' : `${weekOffset} Weeks Ago`;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CalendarDays className="w-6 h-6 text-primary" />
            Weekly Digest
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            {digest ? `${digest.week_start} — ${digest.week_end}` : 'Loading...'}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="text-sm px-3 py-1.5 rounded-md border hover:bg-muted transition-colors"
            disabled={loading}
            onClick={() => setWeekOffset((w) => w + 1)}
          >
            ← Previous
          </button>
          <span className="text-sm px-3 py-1.5 font-medium">{weekLabel}</span>
          <button
            className="text-sm px-3 py-1.5 rounded-md border hover:bg-muted transition-colors disabled:opacity-40"
            disabled={weekOffset === 0 || loading}
            onClick={() => setWeekOffset((w) => Math.max(0, w - 1))}
          >
            Next →
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-muted-foreground text-center py-12">Loading digest...</p>
      ) : !digest ? null : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <FinancialCard>
              <FinancialCardContent className="pt-4">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Total Spent</p>
                  <p className="text-2xl font-bold text-destructive">
                    {formatMoney(digest.summary.total_spent, 'INR')}
                  </p>
                  <WowBadge pct={digest.summary.wow_change_pct} />
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardContent className="pt-4">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Total Income</p>
                  <p className="text-2xl font-bold text-success">
                    {formatMoney(digest.summary.total_income, 'INR')}
                  </p>
                  <span className="text-xs text-muted-foreground">This week</span>
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardContent className="pt-4">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Net Flow</p>
                  <p className={`text-2xl font-bold ${digest.summary.net_flow >= 0 ? 'text-success' : 'text-destructive'}`}>
                    {formatMoney(digest.summary.net_flow, 'INR')}
                  </p>
                  <span className="text-xs text-muted-foreground">Income − Expenses</span>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Category breakdown */}
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Receipt className="w-4 h-4" /> Spending by Category
                </FinancialCardTitle>
                <FinancialCardDescription>
                  {digest.top_spending_category
                    ? `Top: ${digest.top_spending_category}`
                    : 'No spending this week'}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent className="space-y-3">
                {digest.category_breakdown.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No expenses recorded this week.</p>
                ) : (
                  digest.category_breakdown.map((item) => (
                    <CategoryBar key={item.category} item={item} max={maxCategorySpend} />
                  ))
                )}
              </FinancialCardContent>
            </FinancialCard>

            <div className="space-y-4">
              {/* Insights */}
              <FinancialCard>
                <FinancialCardHeader>
                  <FinancialCardTitle className="flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-warning" /> Insights
                  </FinancialCardTitle>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <ul className="space-y-2">
                    {digest.insights.map((insight, i) => (
                      <li key={i} className="flex gap-2 text-sm">
                        <span className="text-primary mt-0.5">•</span>
                        <span>{insight}</span>
                      </li>
                    ))}
                  </ul>
                </FinancialCardContent>
              </FinancialCard>

              {/* Upcoming bills */}
              {digest.upcoming_bills.length > 0 && (
                <FinancialCard>
                  <FinancialCardHeader>
                    <FinancialCardTitle className="flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-warning" /> Bills Due Soon
                    </FinancialCardTitle>
                  </FinancialCardHeader>
                  <FinancialCardContent className="space-y-2">
                    {digest.upcoming_bills.map((bill) => (
                      <div key={bill.id} className="flex justify-between text-sm">
                        <span>{bill.name}</span>
                        <span className="text-muted-foreground">
                          {formatMoney(bill.amount, bill.currency)} · {new Date(bill.due_date).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </FinancialCardContent>
                </FinancialCard>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
