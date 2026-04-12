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

function currentISOWeek(): string {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const dayOfYear = Math.ceil(
    (now.getTime() - new Date(now.getFullYear(), 0, 1).getTime()) / 86400000 + 1,
  );
  const dayOfWeek = now.getDay() || 7;
  const weekNum = Math.ceil((dayOfYear - dayOfWeek + 10) / 7);
  const year = weekNum === 1 && now.getMonth() === 11 ? now.getFullYear() + 1 : now.getFullYear();
  return `${year}-W${String(weekNum).padStart(2, '0')}`;
}

const PERSONAS = ['Balanced coach', 'Conservative saver', 'Debt-focused planner'];

export function Digest() {
  const { toast } = useToast();
  const [week, setWeek] = useState(currentISOWeek);
  const [persona, setPersona] = useState(PERSONAS[0]);
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
        persona,
        geminiApiKey: geminiKey.trim() || undefined,
      });
      setData(payload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load digest';
      setError(message);
      toast({ title: 'Failed to load digest', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const wowPct = data?.analytics?.week_over_week_change_pct ?? 0;
  const wowLabel = wowPct > 0 ? `+${wowPct.toFixed(2)}%` : `${wowPct.toFixed(2)}%`;

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              Smart weekly financial summary with AI-powered tips.
            </p>
          </div>
          <div className="grid gap-2 md:grid-cols-4">
            <div>
              <Label htmlFor="digest-week">Week</Label>
              <Input
                id="digest-week"
                aria-label="digest week"
                type="text"
                placeholder="YYYY-Wnn"
                value={week}
                onChange={(e) => setWeek(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="digest-persona">Persona</Label>
              <select
                id="digest-persona"
                aria-label="digest persona"
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
              <Label htmlFor="digest-key">Gemini API Key (optional BYOK)</Label>
              <Input
                id="digest-key"
                aria-label="gemini api key"
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIza..."
              />
            </div>
          </div>
          <Button onClick={load} disabled={loading}>
            Load Digest
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="card">Loading digest...</div>
      ) : error ? (
        <div className="card text-red-600">{error}</div>
      ) : data ? (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-4">
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Total Income</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>{formatMoney(data.total_income)}</FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Total Expenses</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>{formatMoney(data.total_expenses)}</FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Net Flow</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <span className={data.net_flow >= 0 ? 'text-green-600' : 'text-red-600'}>
                  {formatMoney(data.net_flow)}
                </span>
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Week-over-Week</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <span className={wowPct <= 0 ? 'text-green-600' : 'text-red-600'}>
                  {wowLabel}
                </span>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {data.analytics.top_categories.length > 0 && (
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Top Categories</FinancialCardTitle>
                <FinancialCardDescription>Highest spending categories this week</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="grid gap-3 md:grid-cols-3">
                  {data.analytics.top_categories.map((cat) => (
                    <div key={cat.category_id} className="rounded-lg border p-3">
                      <div className="text-sm text-muted-foreground">
                        Category {cat.category_id}
                      </div>
                      <div className="font-semibold">{formatMoney(cat.amount)}</div>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}

          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Tips &amp; Insights</FinancialCardTitle>
              <FinancialCardDescription>{data.persona}</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {data.summary && (
                <p className="mb-3 text-sm">{data.summary}</p>
              )}
              {data.tips?.length ? (
                <ul className="list-disc pl-5 space-y-1">
                  {data.tips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              ) : (
                <div className="text-sm text-muted-foreground">
                  No tips available for this week.
                </div>
              )}
              {data.warnings?.length ? (
                <div className="mt-3 text-sm text-amber-700">
                  Warning: {data.warnings.join(', ')}
                </div>
              ) : null}
            </FinancialCardContent>
          </FinancialCard>

          <div className="text-xs text-muted-foreground text-right">
            Method: {data.method} &middot; Week: {data.week}
          </div>
        </div>
      ) : null}
    </div>
  );
}
