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
  getBudgetSuggestion,
  getWeeklySummary,
  type BudgetSuggestion,
  type WeeklySummary,
} from '@/api/insights';
import { formatMoney } from '@/lib/currency';

const PERSONAS = [
  'Balanced coach',
  'Conservative saver',
  'Debt-focused planner',
];

function dateInputValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function currentWeekStart(): string {
  const today = new Date();
  const mondayOffset = (today.getDay() + 6) % 7;
  today.setDate(today.getDate() - mondayOffset);
  return dateInputValue(today);
}

export function Analytics() {
  const { toast } = useToast();
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [weekStart, setWeekStart] = useState(currentWeekStart);
  const [currency, setCurrency] = useState('');
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [geminiKey, setGeminiKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<BudgetSuggestion | null>(null);
  const [weeklyData, setWeeklyData] = useState<WeeklySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [monthlyPayload, weeklyPayload] = await Promise.all([
        getBudgetSuggestion({
          month,
          persona,
          geminiApiKey: geminiKey.trim() || undefined,
        }),
        getWeeklySummary({
          weekStart,
          currency: currency.trim() || undefined,
        }),
      ]);
      setData(monthlyPayload);
      setWeeklyData(weeklyPayload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load insights';
      setError(message);
      toast({ title: 'Failed to load insights', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const breakdown = useMemo(() => {
    if (!data) return [];
    return [
      { label: 'Needs', value: data.breakdown.needs },
      { label: 'Wants', value: data.breakdown.wants },
      { label: 'Savings', value: data.breakdown.savings },
    ];
  }, [data]);

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Financial Analytics</h1>
            <p className="page-subtitle">
              Live spending analytics with Gemini-powered budget coaching.
            </p>
          </div>
          <div className="grid gap-2 md:grid-cols-6">
            <div>
              <Label htmlFor="analytics-month">Month</Label>
              <Input
                id="analytics-month"
                aria-label="analytics month"
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="analytics-week">Week Start</Label>
              <Input
                id="analytics-week"
                aria-label="analytics week start"
                type="date"
                value={weekStart}
                onChange={(e) => setWeekStart(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="analytics-currency">Currency</Label>
              <Input
                id="analytics-currency"
                aria-label="analytics currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                placeholder="Default"
                maxLength={10}
              />
            </div>
            <div>
              <Label htmlFor="analytics-persona">Persona</Label>
              <select
                id="analytics-persona"
                aria-label="analytics persona"
                className="input"
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
              >
                {PERSONAS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <Label htmlFor="analytics-key">Gemini API Key (optional BYOK)</Label>
              <Input
                id="analytics-key"
                aria-label="gemini api key"
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIza..."
              />
            </div>
          </div>
          <Button onClick={load} disabled={loading}>
            Refresh Insights
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="card">Loading analytics...</div>
      ) : error ? (
        <div className="card text-red-600">{error}</div>
      ) : data ? (
        <div className="space-y-6">
          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Weekly Smart Digest</FinancialCardTitle>
              <FinancialCardDescription>
                {weeklyData
                  ? `${weeklyData.period.week_start} to ${weeklyData.period.week_end}`
                  : 'Current week'}
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-lg border p-3">
                  <div className="text-sm text-muted-foreground">Weekly Expenses</div>
                  <div className="font-semibold">
                    {formatMoney(weeklyData?.summary.expenses || 0, weeklyData?.currency)}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-sm text-muted-foreground">Net Flow</div>
                  <div className="font-semibold">
                    {formatMoney(weeklyData?.summary.net_flow || 0, weeklyData?.currency)}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-sm text-muted-foreground">Week Over Week</div>
                  <div className="font-semibold">
                    {weeklyData?.comparison.expense_change_pct.toFixed(2) || '0.00'}%
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-sm text-muted-foreground">Bills Due</div>
                  <div className="font-semibold">{weeklyData?.upcoming_bills.length || 0}</div>
                </div>
              </div>

              {weeklyData ? (
                <div className="mt-4 grid gap-4 lg:grid-cols-3">
                  <div className="rounded-lg border p-3">
                    <div className="text-sm font-semibold">Daily Spend</div>
                    <div className="mt-3 space-y-2">
                      {weeklyData.daily_breakdown.map((day) => {
                        const max = Math.max(
                          ...weeklyData.daily_breakdown.map((item) => item.expenses),
                          1,
                        );
                        return (
                          <div key={day.date} className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span>{day.day}</span>
                              <span>{formatMoney(day.expenses, weeklyData.currency)}</span>
                            </div>
                            <div className="h-2 rounded-full bg-muted">
                              <div
                                className="h-2 rounded-full bg-primary"
                                style={{ width: `${Math.round((day.expenses / max) * 100)}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="rounded-lg border p-3">
                    <div className="text-sm font-semibold">Top Categories</div>
                    <div className="mt-3 space-y-2">
                      {weeklyData.category_breakdown.length ? (
                        weeklyData.category_breakdown.slice(0, 4).map((category) => (
                          <div key={`${category.category_id}-${category.category_name}`}>
                            <div className="flex justify-between text-xs">
                              <span>{category.category_name}</span>
                              <span>{category.share_pct.toFixed(1)}%</span>
                            </div>
                            <div className="text-sm font-medium">
                              {formatMoney(category.amount, weeklyData.currency)}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-muted-foreground">No category spend yet.</div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg border p-3">
                    <div className="text-sm font-semibold">Recommended Actions</div>
                    <ul className="mt-3 list-disc pl-5 text-sm space-y-1">
                      {weeklyData.recommendations.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : null}
            </FinancialCardContent>
          </FinancialCard>

          <div className="grid gap-4 md:grid-cols-4">
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Method</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>{data.method}</FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Suggested Budget</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>{formatMoney(data.suggested_total)}</FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">MoM Expense Change</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {data.analytics.month_over_month_change_pct.toFixed(2)}%
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Current Month Expenses</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {formatMoney(data.analytics.current_month_expenses)}
              </FinancialCardContent>
            </FinancialCard>
          </div>

          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Budget Breakdown</FinancialCardTitle>
              <FinancialCardDescription>{data.persona}</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="grid gap-3 md:grid-cols-3">
                {breakdown.map((item) => (
                  <div key={item.label} className="rounded-lg border p-3">
                    <div className="text-sm text-muted-foreground">{item.label}</div>
                    <div className="font-semibold">{formatMoney(item.value)}</div>
                  </div>
                ))}
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Coach Tips</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data.tips?.length ? (
                <ul className="list-disc pl-5 space-y-1">
                  {data.tips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              ) : (
                <div className="text-sm text-muted-foreground">No tips available for this month.</div>
              )}
              {data.warnings?.length ? (
                <div className="mt-3 text-sm text-amber-700">
                  Warning: {data.warnings.join(', ')}
                </div>
              ) : null}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      ) : null}
    </div>
  );
}
