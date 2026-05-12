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
import { getBudgetSuggestion, getWeeklySummary, type BudgetSuggestion, type WeeklySummary } from '@/api/insights';
import { formatMoney } from '@/lib/currency';

const PERSONAS = [
  'Balanced coach',
  'Conservative saver',
  'Debt-focused planner',
];

export function Analytics() {
  const { toast } = useToast();
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [weekStart, setWeekStart] = useState(getCurrentMonday);
  const [currency, setCurrency] = useState('');
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [geminiKey, setGeminiKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<BudgetSuggestion | null>(null);
  const [weekly, setWeekly] = useState<WeeklySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [payload, weeklyPayload] = await Promise.all([
        getBudgetSuggestion({
          month,
          persona,
          geminiApiKey: geminiKey.trim() || undefined,
        }),
        getWeeklySummary({
          weekStart,
          currency: currency.trim().toUpperCase() || undefined,
        }),
      ]);
      setData(payload);
      setWeekly(weeklyPayload);
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
          <div className="grid gap-2 md:grid-cols-4">
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
                aria-label="weekly summary week start"
                type="date"
                value={weekStart}
                onChange={(e) => setWeekStart(e.target.value)}
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
            <div>
              <Label htmlFor="analytics-currency">Currency</Label>
              <Input
                id="analytics-currency"
                aria-label="weekly summary currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                placeholder="All"
                maxLength={10}
              />
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
          {weekly ? (
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Weekly Digest</FinancialCardTitle>
                <FinancialCardDescription>
                  {weekly.period.week_start} to {weekly.period.week_end}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="grid gap-3 md:grid-cols-4">
                  <div className="rounded-lg border p-3">
                    <div className="text-sm text-muted-foreground">Income</div>
                    <div className="font-semibold">
                      {formatMoney(weekly.summary.income, weekly.period.currency || undefined)}
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-sm text-muted-foreground">Expenses</div>
                    <div className="font-semibold">
                      {formatMoney(weekly.summary.expenses, weekly.period.currency || undefined)}
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-sm text-muted-foreground">Net Flow</div>
                    <div className="font-semibold">
                      {formatMoney(weekly.summary.net_flow, weekly.period.currency || undefined)}
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-sm text-muted-foreground">Vs Last Week</div>
                    <div className="font-semibold">
                      {formatMoney(weekly.previous_week.expense_delta, weekly.period.currency || undefined)}
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="mb-2 text-sm font-semibold">Top Categories</div>
                    {weekly.category_breakdown.length ? (
                      <div className="space-y-2">
                        {weekly.category_breakdown.slice(0, 4).map((item) => (
                          <div key={`${item.category_id}-${item.category_name}`} className="rounded-lg border p-3">
                            <div className="flex items-center justify-between gap-3">
                              <span className="font-medium">{item.category_name}</span>
                              <span>{formatMoney(item.amount, weekly.period.currency || undefined)}</span>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {item.share_pct}% of weekly expenses, change {formatMoney(item.change_amount, weekly.period.currency || undefined)}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-sm text-muted-foreground">No category spending this week.</div>
                    )}
                  </div>
                  <div>
                    <div className="mb-2 text-sm font-semibold">Smart Signals</div>
                    <div className="space-y-2">
                      {weekly.insights.map((item) => (
                        <div key={`${item.type}-${item.message}`} className="rounded-lg border p-3 text-sm">
                          {item.message}
                        </div>
                      ))}
                      {weekly.upcoming_bills.length ? (
                        <div className="rounded-lg border p-3 text-sm">
                          Next bill: {weekly.upcoming_bills[0].name} on {weekly.upcoming_bills[0].next_due_date}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ) : null}

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

function getCurrentMonday() {
  const now = new Date();
  const day = now.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  now.setDate(now.getDate() + diff);
  return now.toISOString().slice(0, 10);
}
