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
import { getWeeklyDigest, type WeeklyDigest } from '@/api/digest';
import { formatMoney } from '@/lib/currency';

function getMondayOfWeek(date: Date): string {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  d.setDate(diff);
  return d.toISOString().slice(0, 10);
}

export function Digest() {
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
      toast({ title: 'Digest unavailable', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="page-wrap space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="space-y-1.5">
          <Label htmlFor="week">Week of</Label>
          <Input id="week" type="date" value={week} onChange={(e) => setWeek(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="gemini-key">Gemini API Key (optional)</Label>
          <Input id="gemini-key" type="password" placeholder="AI-powered insights" value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} />
        </div>
        <Button onClick={() => void load()} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </Button>
      </div>

      {error && <p className="text-destructive text-sm">{error}</p>}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Income</FinancialCardTitle>
                <FinancialCardDescription>
                  {data.wow_income_change_pct != null
                    ? `${data.wow_income_change_pct > 0 ? '+' : ''}${data.wow_income_change_pct.toFixed(1)}% vs last week`
                    : 'No prior week data'}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <span className="text-2xl font-bold text-green-500">{formatMoney(data.total_income)}</span>
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Expenses</FinancialCardTitle>
                <FinancialCardDescription>
                  {data.wow_expense_change_pct != null
                    ? `${data.wow_expense_change_pct > 0 ? '+' : ''}${data.wow_expense_change_pct.toFixed(1)}% vs last week`
                    : 'No prior week data'}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <span className="text-2xl font-bold text-red-500">{formatMoney(data.total_expenses)}</span>
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Net Flow</FinancialCardTitle>
                <FinancialCardDescription>{data.transaction_count} transactions</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <span className={`text-2xl font-bold ${data.net_flow >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {formatMoney(data.net_flow)}
                </span>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {data.category_breakdown.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Spending by Category</FinancialCardTitle>
                <FinancialCardDescription>
                  {data.week_start} to {data.week_end}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  {data.category_breakdown.map((cat) => (
                    <div key={cat.category} className="flex items-center justify-between">
                      <span className="text-sm font-medium">{cat.category}</span>
                      <div className="flex items-center gap-3">
                        <div className="h-2 w-24 rounded-full bg-muted overflow-hidden">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(cat.percentage, 100)}%` }} />
                        </div>
                        <span className="text-sm tabular-nums">{formatMoney(cat.amount)} ({cat.percentage.toFixed(0)}%)</span>
                      </div>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {data.daily_breakdown.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Daily Spending</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="flex items-end gap-2 h-32">
                  {data.daily_breakdown.map((day) => {
                    const max = Math.max(...data.daily_breakdown.map((d) => d.amount), 1);
                    const pct = (day.amount / max) * 100;
                    return (
                      <div key={day.day} className="flex-1 flex flex-col items-center gap-1">
                        <div className="w-full bg-primary/80 rounded-t" style={{ height: `${Math.max(pct, 4)}%` }} />
                        <span className="text-[10px] text-muted-foreground">{new Date(day.day).toLocaleDateString('en', { weekday: 'short' })}</span>
                      </div>
                    );
                  })}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {data.insights.length > 0 && (
            <FinancialCard>
              <FinancialCardHeader>
                <FinancialCardTitle>Insights</FinancialCardTitle>
                <FinancialCardDescription>
                  Powered by {data.method === 'gemini' ? 'Gemini AI' : 'heuristic analysis'}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="list-disc pl-5 space-y-1.5 text-sm">
                  {data.insights.map((insight, i) => (
                    <li key={i}>{insight}</li>
                  ))}
                </ul>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {data.warnings && data.warnings.length > 0 && (
            <div className="rounded-md border border-yellow-500/50 bg-yellow-500/10 p-4">
              <p className="text-sm font-medium text-yellow-500">Warnings</p>
              <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-yellow-400">
                {data.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
