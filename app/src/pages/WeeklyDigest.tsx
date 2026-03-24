import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  ArrowDownRight,
  ArrowUpRight,
  TrendingDown,
  TrendingUp,
  Lightbulb,
  BarChart2,
  Calendar,
} from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigest } from '@/api/insights';
import { formatMoney } from '@/lib/currency';
import { useToast } from '@/hooks/use-toast';

function getMondayOfWeek(d: Date): string {
  const day = d.getDay();
  const diff = (day === 0 ? -6 : 1) - day;
  const monday = new Date(d);
  monday.setDate(d.getDate() + diff);
  return monday.toISOString().slice(0, 10);
}

export function WeeklyDigest() {
  const { toast } = useToast();
  const [week, setWeek] = useState(() => getMondayOfWeek(new Date()));
  const [geminiKey, setGeminiKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<WeeklyDigest | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await getWeeklyDigest({
        week,
        geminiApiKey: geminiKey.trim() || undefined,
      });
      setData(payload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load digest';
      setError(message);
      toast({ title: 'Failed to load weekly digest', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const wowPositive = data ? data.week_over_week_change_pct > 0 : false;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Weekly Digest</h1>
        <p className="text-muted-foreground text-sm">
          Trends &amp; insights for your financial week at a glance.
        </p>
      </div>

      {/* Controls */}
      <FinancialCard>
        <FinancialCardHeader>
          <FinancialCardTitle>
            <Calendar className="inline-block w-4 h-4 mr-2" />
            Select Week
          </FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent className="flex flex-wrap gap-4 items-end">
          <div className="flex flex-col gap-1">
            <Label htmlFor="week-input">Week starting (Monday)</Label>
            <Input
              id="week-input"
              type="date"
              value={week}
              onChange={(e) => setWeek(e.target.value)}
              className="w-44"
            />
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-48">
            <Label htmlFor="gemini-key">Gemini API Key (optional, for AI insights)</Label>
            <Input
              id="gemini-key"
              type="password"
              placeholder="AIza..."
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
            />
          </div>
          <Button onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
        </FinancialCardContent>
      </FinancialCard>

      {error && (
        <div className="text-destructive text-sm border border-destructive/30 rounded-lg p-4">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardDescription>Total Expenses</FinancialCardDescription>
                <FinancialCardTitle className="text-xl">
                  {formatMoney(data.total_expenses)}
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent className="flex items-center gap-1 text-sm">
                {wowPositive ? (
                  <ArrowUpRight className="w-4 h-4 text-destructive" />
                ) : (
                  <ArrowDownRight className="w-4 h-4 text-green-500" />
                )}
                <span className={wowPositive ? 'text-destructive' : 'text-green-500'}>
                  {Math.abs(data.week_over_week_change_pct)}% vs last week
                </span>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardDescription>Total Income</FinancialCardDescription>
                <FinancialCardTitle className="text-xl">
                  {formatMoney(data.total_income)}
                </FinancialCardTitle>
              </FinancialCardHeader>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardDescription>Net Flow</FinancialCardDescription>
                <FinancialCardTitle
                  className={`text-xl ${data.net_flow >= 0 ? 'text-green-500' : 'text-destructive'}`}
                >
                  {formatMoney(data.net_flow)}
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent className="flex items-center gap-1 text-sm text-muted-foreground">
                {data.net_flow >= 0 ? (
                  <TrendingUp className="w-4 h-4 text-green-500" />
                ) : (
                  <TrendingDown className="w-4 h-4 text-destructive" />
                )}
                <span>{data.net_flow >= 0 ? 'In the green' : 'Over budget'}</span>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardDescription>Previous Week</FinancialCardDescription>
                <FinancialCardTitle className="text-xl">
                  {formatMoney(data.previous_week_expenses)}
                </FinancialCardTitle>
              </FinancialCardHeader>
            </FinancialCard>
          </div>

          {/* Top categories */}
          {data.top_categories.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>
                  <BarChart2 className="inline-block w-4 h-4 mr-2" />
                  Top Spending Categories
                </FinancialCardTitle>
                <FinancialCardDescription>
                  {data.week_start} – {data.week_end}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="space-y-2">
                  {data.top_categories.map((cat) => (
                    <li key={cat.category} className="flex justify-between items-center text-sm">
                      <span className="font-medium">{cat.category}</span>
                      <span className="text-muted-foreground">{formatMoney(cat.amount)}</span>
                    </li>
                  ))}
                </ul>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {/* Daily breakdown */}
          {data.daily_breakdown.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Day-by-Day Spending</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="flex flex-col gap-2">
                  {data.daily_breakdown.map((day) => (
                    <div key={day.date} className="flex justify-between items-center text-sm">
                      <span className="text-muted-foreground">
                        {new Date(day.date + 'T12:00:00').toLocaleDateString(undefined, {
                          weekday: 'short',
                          month: 'short',
                          day: 'numeric',
                        })}
                      </span>
                      <span className="font-medium">{formatMoney(day.amount)}</span>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {/* AI / Heuristic insights */}
          {data.insights.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>
                  <Lightbulb className="inline-block w-4 h-4 mr-2 text-yellow-500" />
                  Insights
                  {data.method === 'gemini' && (
                    <span className="ml-2 text-xs text-muted-foreground font-normal">
                      AI-powered
                    </span>
                  )}
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="list-disc list-inside space-y-1 text-sm">
                  {data.insights.map((tip, i) => (
                    <li key={i}>{tip}</li>
                  ))}
                </ul>
                {data.warnings?.includes('gemini_unavailable') && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    ⚠ AI insights unavailable — showing rule-based insights.
                  </p>
                )}
              </FinancialCardContent>
            </FinancialCard>
          )}
        </>
      )}
    </div>
  );
}
