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
import { getBudgetSuggestion, type BudgetSuggestion } from '@/api/insights';
import { formatMoney } from '@/lib/currency';

const PERSONAS = [
  'Balanced coach',
  'Conservative saver',
  'Debt-focused planner',
];

export function Analytics() {
  const { toast } = useToast();
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [geminiKey, setGeminiKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<BudgetSuggestion | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await getBudgetSuggestion({
        month,
        persona,
        geminiApiKey: geminiKey.trim() || undefined,
      });
      setData(payload);
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
