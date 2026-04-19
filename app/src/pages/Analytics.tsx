import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import { getBudgetSuggestion, getWeeklyDigest, type BudgetSuggestion, type WeeklyDigest } from '@/api/insights';
import { formatMoney } from '@/lib/currency';

const PERSONAS = [
  'Balanced coach',
  'Conservative saver',
  'Debt-focused planner',
];

export function Analytics() {
  const { toast } = useToast();
  const [viewType, setViewType] = useState<'monthly' | 'weekly'>('monthly');
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  
  // Weekly dates
  const today = new Date();
  const startOfWeek = new Date(today);
  startOfWeek.setDate(today.getDate() - today.getDay());
  const [weekStart, setWeekStart] = useState(() => startOfWeek.toISOString().slice(0, 10));
  
  const endOfWeek = new Date(startOfWeek);
  endOfWeek.setDate(startOfWeek.getDate() + 6);
  const [weekEnd, setWeekEnd] = useState(() => endOfWeek.toISOString().slice(0, 10));

  const [persona, setPersona] = useState(PERSONAS[0]);
  const [geminiKey, setGeminiKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<BudgetSuggestion | WeeklyDigest | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      if (viewType === 'monthly') {
        const payload = await getBudgetSuggestion({
          month,
          persona,
          geminiApiKey: geminiKey.trim() || undefined,
        });
        setData(payload);
      } else {
        const payload = await getWeeklyDigest({
          weekStart,
          weekEnd,
          persona,
          geminiApiKey: geminiKey.trim() || undefined,
        });
        setData(payload);
      }
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
  }, [viewType]);

  const breakdown = useMemo(() => {
    if (!data || !data.breakdown) return [];
    return [
      { label: 'Needs', value: data.breakdown.needs },
      { label: 'Wants', value: data.breakdown.wants },
      { label: 'Savings', value: data.breakdown.savings },
    ];
  }, [data]);

  const isWeekly = viewType === 'weekly';
  const analyticsData = data?.analytics as any;

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
          
          <div className="flex gap-2">
            <Button 
              variant={viewType === 'monthly' ? 'default' : 'outline'} 
              onClick={() => setViewType('monthly')}
            >
              Monthly Budget
            </Button>
            <Button 
              variant={viewType === 'weekly' ? 'default' : 'outline'} 
              onClick={() => setViewType('weekly')}
            >
              Weekly Digest
            </Button>
          </div>
          
          <div className="grid gap-2 md:grid-cols-4">
            {isWeekly ? (
              <>
                <div>
                  <Label htmlFor="analytics-week-start">Week Start</Label>
                  <Input
                    id="analytics-week-start"
                    type="date"
                    value={weekStart}
                    onChange={(e) => setWeekStart(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="analytics-week-end">Week End</Label>
                  <Input
                    id="analytics-week-end"
                    type="date"
                    value={weekEnd}
                    onChange={(e) => setWeekEnd(e.target.value)}
                  />
                </div>
              </>
            ) : (
              <div className="md:col-span-2">
                <Label htmlFor="analytics-month">Month</Label>
                <Input
                  id="analytics-month"
                  aria-label="analytics month"
                  type="month"
                  value={month}
                  onChange={(e) => setMonth(e.target.value)}
                />
              </div>
            )}
            
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
              <Label htmlFor="analytics-key">Gemini API Key</Label>
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
          {isWeekly && (data as WeeklyDigest).summary && (
            <FinancialCard variant="financial" className="bg-primary/5 border-primary/20">
              <FinancialCardHeader>
                <FinancialCardTitle className="text-xl">Weekly Summary</FinancialCardTitle>
                {data.score && <Badge variant="secondary">Health Score: {data.score}/100</Badge>}
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-lg">{(data as WeeklyDigest).summary}</p>
                {(data as WeeklyDigest).highlighted_trend && (
                  <p className="mt-2 text-sm font-medium text-amber-700">
                    💡 Trend: {(data as WeeklyDigest).highlighted_trend}
                  </p>
                )}
              </FinancialCardContent>
            </FinancialCard>
          )}
          
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
              <FinancialCardContent>{formatMoney(data.suggested_total || 0)}</FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">
                  {isWeekly ? 'WoW Expense Change' : 'MoM Expense Change'}
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {isWeekly 
                  ? analyticsData?.week_over_week_change_pct?.toFixed(2)
                  : analyticsData?.month_over_month_change_pct?.toFixed(2)}%
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">
                  {isWeekly ? 'Current Week Expenses' : 'Current Month Expenses'}
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {formatMoney(isWeekly 
                  ? analyticsData?.current_week_expenses
                  : analyticsData?.current_month_expenses)}
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
              <FinancialCardTitle>{isWeekly ? 'Action Items & Tips' : 'Coach Tips'}</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              {isWeekly && (data as WeeklyDigest).action_items?.length ? (
                <div className="mb-4">
                  <h4 className="font-semibold mb-2">Action Items:</h4>
                  <ul className="list-disc pl-5 space-y-1 text-primary">
                    {(data as WeeklyDigest).action_items?.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              
              {data.tips?.length ? (
                <div>
                  {isWeekly && <h4 className="font-semibold mb-2">General Tips:</h4>}
                  <ul className="list-disc pl-5 space-y-1">
                    {data.tips.map((tip) => (
                      <li key={tip}>{tip}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                !((data as WeeklyDigest).action_items?.length) && 
                <div className="text-sm text-muted-foreground">No tips available for this period.</div>
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
