import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  ArrowLeft,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  Minus,
  Lightbulb,
  BarChart3,
} from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigest } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function isoWeek(d: Date): string {
  const tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  tmp.setUTCDate(tmp.getUTCDate() + 4 - (tmp.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
  const wk = Math.ceil(((tmp.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${tmp.getUTCFullYear()}-W${String(wk).padStart(2, '0')}`;
}

function shiftWeek(week: string, delta: number): string {
  const [yearStr, wStr] = week.split('-W');
  const year = parseInt(yearStr, 10);
  const w = parseInt(wStr, 10);
  const monday = new Date(Date.UTC(year, 0, 4));
  monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() || 7) + 1 + (w - 1) * 7 + delta * 7);
  return isoWeek(monday);
}

export default function Digest() {
  const [week, setWeek] = useState(() => isoWeek(new Date()));
  const [data, setData] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getWeeklyDigest(week);
        setData(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load digest');
      } finally {
        setLoading(false);
      }
    })();
  }, [week]);

  const wowChange = data?.week_over_week_change ?? 0;
  const WowIcon = wowChange > 0 ? TrendingUp : wowChange < 0 ? TrendingDown : Minus;
  const wowColor = wowChange > 0 ? 'text-red-500' : wowChange < 0 ? 'text-green-500' : 'text-muted-foreground';
  const wowBadgeVariant = wowChange > 0 ? 'destructive' : wowChange < 0 ? 'default' : 'secondary';

  return (
    <div className="container mx-auto p-4 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Weekly Digest</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setWeek((w) => shiftWeek(w, -1))}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium min-w-[90px] text-center">{week}</span>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setWeek((w) => shiftWeek(w, 1))}
            disabled={week >= isoWeek(new Date())}
          >
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {data?.period && (
        <p className="text-sm text-muted-foreground">
          {data.period.start} — {data.period.end}
        </p>
      )}

      {loading && <p className="text-muted-foreground">Loading...</p>}
      {error && <p className="text-destructive">{error}</p>}

      {!loading && data && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Total Spent</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-2xl font-bold">{formatMoney(data.total_spent)}</p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Total Income</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-2xl font-bold">{formatMoney(data.total_income)}</p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Week-over-Week</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="flex items-center gap-2">
                  <WowIcon className={`h-5 w-5 ${wowColor}`} />
                  <Badge variant={wowBadgeVariant as 'default' | 'secondary' | 'destructive' | 'outline'}>
                    {wowChange > 0 ? '+' : ''}{wowChange}%
                  </Badge>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {data.category_breakdown.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" /> Category Breakdown
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  {data.category_breakdown.map((cat) => (
                    <div key={cat.category_id ?? 'uncat'} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span>{cat.category_name}</span>
                        <span className="text-muted-foreground">
                          {formatMoney(cat.amount)} ({cat.share_pct}%)
                        </span>
                      </div>
                      <Progress value={cat.share_pct} className="h-2" />
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {data.trends.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" /> Trends
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="space-y-2">
                  {data.trends.map((t, i) => (
                    <li key={i} className="text-sm text-muted-foreground">
                      • {t}
                    </li>
                  ))}
                </ul>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {data.insights.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Lightbulb className="h-5 w-5" /> Insights
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="space-y-2">
                  {data.insights.map((ins, i) => (
                    <li key={i} className="text-sm text-muted-foreground">
                      • {ins}
                    </li>
                  ))}
                </ul>
              </FinancialCardContent>
            </FinancialCard>
          )}
        </>
      )}
    </div>
  );
}
