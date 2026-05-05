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
  TrendingDown,
  TrendingUp,
  Minus,
  Calendar,
  AlertCircle,
  Wallet,
  Receipt,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigest, type WeeklyBreakdown } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function TrendBadge({ trend, delta, deltaPct }: { trend: string; delta: number | null; deltaPct: number | null }) {
  if (delta === null) return <Badge variant="outline">Baseline</Badge>;
  if (trend === 'up') return (
    <Badge variant="destructive" className="gap-1">
      <TrendingUp className="h-3 w-3" />
      +{formatMoney(Math.abs(delta))} ({deltaPct}%)
    </Badge>
  );
  if (trend === 'down') return (
    <Badge variant="default" className="gap-1 bg-green-600">
      <TrendingDown className="h-3 w-3" />
      -{formatMoney(Math.abs(delta))} ({Math.abs(deltaPct || 0)}%)
    </Badge>
  );
  return <Badge variant="outline" className="gap-1"><Minus className="h-3 w-3" />Flat</Badge>;
}

function WeekCard({ week }: { week: WeeklyBreakdown }) {
  return (
    <FinancialCard className="mb-3">
      <FinancialCardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <FinancialCardTitle className="text-sm font-medium">
              Week of {week.week_start}
            </FinancialCardTitle>
            <FinancialCardDescription>
              {week.week_start} → {week.week_end} · {week.txn_count} transactions
            </FinancialCardDescription>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold">{formatMoney(week.total)}</div>
            <TrendBadge trend={week.trend} delta={week.wow_delta} deltaPct={week.wow_delta_pct} />
          </div>
        </div>
      </FinancialCardHeader>
      {week.categories.length > 0 && (
        <FinancialCardContent>
          <div className="space-y-1">
            {week.categories.map((cat) => (
              <div key={cat.category} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{cat.category}</span>
                <span className="font-medium">{formatMoney(cat.amount)}</span>
              </div>
            ))}
          </div>
        </FinancialCardContent>
      )}
    </FinancialCard>
  );
}

export function Digest() {
  const [data, setData] = useState<WeeklyDigest | null>(null);
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
      <div className="container mx-auto max-w-4xl space-y-4 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="container mx-auto max-w-4xl p-6">
        <FinancialCard>
          <FinancialCardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-destructive">{error || 'No data available'}</p>
          </FinancialCardContent>
        </FinancialCard>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Weekly Digest</h1>
          <p className="text-muted-foreground">
            {data.period.from} → {data.period.to}
          </p>
        </div>
        <div className="flex gap-2">
          {[4, 8, 12].map((w) => (
            <Button
              key={w}
              variant={weeks === w ? 'default' : 'outline'}
              size="sm"
              onClick={() => setWeeks(w)}
            >
              {w}w
            </Button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Total Spending</FinancialCardDescription>
            <FinancialCardTitle className="text-xl">
              {formatMoney(data.summary.total_spending)}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Weekly Average</FinancialCardDescription>
            <FinancialCardTitle className="text-xl">
              {formatMoney(data.summary.average_weekly)}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Transactions</FinancialCardDescription>
            <FinancialCardTitle className="text-xl">
              {data.summary.total_transactions}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Upcoming Bills</FinancialCardDescription>
            <FinancialCardTitle className="text-xl">
              {data.upcoming_bills.length}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
      </div>

      {/* Top Categories */}
      {data.top_categories.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="text-base">Top Categories</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-2">
              {data.top_categories.map((cat) => (
                <div key={cat.category} className="flex items-center justify-between">
                  <span>{cat.category}</span>
                  <span className="font-medium">{formatMoney(cat.total)}</span>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Weekly Breakdown */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Weekly Breakdown</h2>
        {data.weekly_breakdown.map((week) => (
          <WeekCard key={week.week_start} week={week} />
        ))}
      </div>

      {/* Upcoming Bills */}
      {data.upcoming_bills.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="text-base">
              <Calendar className="mr-2 inline h-4 w-4" />
              Upcoming Bills (Next 7 Days)
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-2">
              {data.upcoming_bills.map((bill) => (
                <div key={bill.id} className="flex items-center justify-between text-sm">
                  <div>
                    <span className="font-medium">{bill.name}</span>
                    <span className="ml-2 text-muted-foreground">
                      Due {bill.due_date} · {bill.cadence}
                    </span>
                  </div>
                  <span className="font-bold">{formatMoney(bill.amount, bill.currency)}</span>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}
    </div>
  );
}
