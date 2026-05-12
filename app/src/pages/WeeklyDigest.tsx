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
import { getWeeklyDigest, type WeeklyDigest } from '@/api/weeklyDigest';

const PERSONAS = [
  'Balanced coach',
  'Conservative saver',
  'Debt-focused planner',
];

const toneClass = {
  positive: 'text-success',
  negative: 'text-destructive',
  neutral: 'text-muted-foreground',
} as const;

export function WeeklyDigestPage() {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [geminiKey, setGeminiKey] = useState('');
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await getWeeklyDigest({
        month,
        persona,
        geminiApiKey: geminiKey.trim() || undefined,
      });
      setDigest(payload);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to generate weekly digest');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const shareText = useMemo(() => {
    if (!digest) return '';
    return [
      `FinMind Weekly Digest (${digest.weekStart} → ${digest.weekEnd})`,
      digest.headline,
      '',
      'Top insights:',
      ...digest.insights.map((item) => `• ${item}`),
      '',
      'Action items:',
      ...digest.actionItems.map((item) => `• ${item}`),
    ].join('\n');
  }, [digest]);

  async function copyDigest() {
    if (!shareText) return;
    await navigator.clipboard?.writeText(shareText);
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="page-title">Weekly Financial Digest</h1>
            <p className="page-subtitle">
              A narrative summary of trends, upcoming bills, and AI-powered budget guidance.
            </p>
          </div>
          <div className="grid gap-2 md:grid-cols-4">
            <div>
              <Label htmlFor="digest-month">Month</Label>
              <Input
                id="digest-month"
                aria-label="digest month"
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
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
                aria-label="digest gemini api key"
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIza..."
              />
            </div>
          </div>
          <Button onClick={load} disabled={loading}>
            Generate Digest
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="card">Generating weekly digest...</div>
      ) : error ? (
        <div className="card text-red-600">{error}</div>
      ) : digest ? (
        <div className="space-y-6">
          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>{digest.headline}</FinancialCardTitle>
              <FinancialCardDescription>
                {digest.weekStart} → {digest.weekEnd}
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-sm text-muted-foreground">{digest.summary}</p>
            </FinancialCardContent>
          </FinancialCard>

          <div className="grid gap-4 md:grid-cols-4">
            {digest.trends.map((trend) => (
              <FinancialCard key={trend.label} variant="financial">
                <FinancialCardHeader className="pb-2">
                  <FinancialCardTitle className="text-sm">{trend.label}</FinancialCardTitle>
                </FinancialCardHeader>
                <FinancialCardContent className={`text-xl font-semibold ${toneClass[trend.tone]}`}>
                  {trend.value}
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Highlights</FinancialCardTitle>
                <FinancialCardDescription>Trends worth noticing this week</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="list-disc space-y-2 pl-5">
                  {digest.insights.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Action Items</FinancialCardTitle>
                <FinancialCardDescription>Small next steps for the coming week</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="list-disc space-y-2 pl-5">
                  {digest.actionItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <Button className="mt-5" variant="outline" onClick={copyDigest}>
                  Copy Digest
                </Button>
              </FinancialCardContent>
            </FinancialCard>
          </div>
        </div>
      ) : null}
    </div>
  );
}
