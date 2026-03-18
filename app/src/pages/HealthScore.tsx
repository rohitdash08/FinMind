import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  getHealthScore,
  getHealthScoreHistory,
  getHealthScoreTips,
  type HealthScore,
  type HealthScoreHistory,
  type HealthScoreTips,
} from '@/api/health-score';
import { useToast } from '@/hooks/use-toast';
import { TrendingUp, TrendingDown, Minus, RefreshCw, Lightbulb } from 'lucide-react';

// ---------------------------------------------------------------------------
// Grade ring colours
// ---------------------------------------------------------------------------

function gradeColor(grade: string): string {
  switch (grade) {
    case 'A': return '#22c55e'; // green-500
    case 'B': return '#84cc16'; // lime-500
    case 'C': return '#eab308'; // yellow-500
    case 'D': return '#f97316'; // orange-500
    default:  return '#ef4444'; // red-500
  }
}

function gradeLabel(grade: string): string {
  switch (grade) {
    case 'A': return 'Excellent';
    case 'B': return 'Good';
    case 'C': return 'Fair';
    case 'D': return 'Needs Work';
    default:  return 'Critical';
  }
}

// ---------------------------------------------------------------------------
// SVG gauge / ring
// ---------------------------------------------------------------------------

interface ScoreRingProps {
  score: number;
  grade: string;
}

function ScoreRing({ score, grade }: ScoreRingProps) {
  const r = 54;
  const circumference = 2 * Math.PI * r;
  const filled = (score / 100) * circumference;
  const color = gradeColor(grade);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="140" height="140" viewBox="0 0 140 140" aria-label={`Health score: ${score} out of 100`}>
        {/* track */}
        <circle
          cx="70" cy="70" r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="12"
          className="text-muted/30"
        />
        {/* filled arc — rotated so it starts at 12 o'clock */}
        <circle
          cx="70" cy="70" r={r}
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
          transform="rotate(-90 70 70)"
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
        <text x="70" y="66" textAnchor="middle" fontSize="28" fontWeight="700" fill={color}>
          {Math.round(score)}
        </text>
        <text x="70" y="84" textAnchor="middle" fontSize="12" fill="currentColor" opacity="0.6">
          / 100
        </text>
      </svg>
      <div className="flex items-center gap-2">
        <span
          className="inline-flex h-7 w-7 items-center justify-center rounded-full text-sm font-extrabold text-white"
          style={{ backgroundColor: color }}
        >
          {grade}
        </span>
        <span className="text-sm font-semibold text-foreground">{gradeLabel(grade)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metric bar
// ---------------------------------------------------------------------------

interface MetricBarProps {
  label: string;
  points: number;
  max: number;
  colorClass?: string;
}

function MetricBar({ label, points, max, colorClass = 'bg-primary' }: MetricBarProps) {
  const pct = max > 0 ? Math.min(100, (points / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="text-foreground font-medium">{label}</span>
        <span className="text-muted-foreground">
          {points.toFixed(1)} / {max}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted/40 overflow-hidden">
        <div
          className={`h-2 rounded-full ${colorClass}`}
          style={{ width: `${pct}%`, transition: 'width 0.5s ease' }}
        />
      </div>
    </div>
  );
}

function metricColor(points: number, max: number): string {
  const ratio = max > 0 ? points / max : 0;
  if (ratio >= 0.8) return 'bg-green-500';
  if (ratio >= 0.6) return 'bg-lime-500';
  if (ratio >= 0.4) return 'bg-yellow-500';
  if (ratio >= 0.2) return 'bg-orange-500';
  return 'bg-red-500';
}

// ---------------------------------------------------------------------------
// Trend icon
// ---------------------------------------------------------------------------

interface TrendIconProps {
  changePct: number | null | undefined;
}

function TrendIcon({ changePct }: TrendIconProps) {
  if (changePct == null) return <Minus className="w-4 h-4 text-muted-foreground" />;
  if (changePct < 0) return <TrendingDown className="w-4 h-4 text-green-500" />;
  if (changePct > 0) return <TrendingUp className="w-4 h-4 text-red-500" />;
  return <Minus className="w-4 h-4 text-muted-foreground" />;
}

// ---------------------------------------------------------------------------
// History mini-bar chart
// ---------------------------------------------------------------------------

interface HistoryChartProps {
  history: HealthScoreHistory['history'];
}

function HistoryChart({ history }: HistoryChartProps) {
  if (!history.length) return null;
  const max = 100;

  return (
    <div className="flex items-end gap-2 h-20">
      {history.map((item) => {
        const heightPct = (item.score / max) * 100;
        const color = gradeColor(item.grade);
        return (
          <div key={item.period} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="w-full rounded-t"
              style={{
                height: `${Math.max(4, heightPct * 0.7)}px`,
                backgroundColor: color,
                transition: 'height 0.4s ease',
              }}
              title={`${item.period}: ${item.score}`}
            />
            <span className="text-[10px] text-muted-foreground truncate">{item.period.slice(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function HealthScorePage() {
  const { toast } = useToast();
  const [score, setScore] = useState<HealthScore | null>(null);
  const [history, setHistory] = useState<HealthScoreHistory | null>(null);
  const [tips, setTips] = useState<HealthScoreTips | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [s, h, t] = await Promise.all([
        getHealthScore(),
        getHealthScoreHistory(),
        getHealthScoreTips(),
      ]);
      setScore(s);
      setHistory(h);
      setTips(t);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load health score';
      setError(msg);
      toast({ title: 'Error', description: msg });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page-wrap space-y-6">
      {/* Header */}
      <div className="page-header">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Financial Health Score</h1>
            <p className="page-subtitle">
              A 0–100 composite of your savings, spending stability, bill reliability and trend.
            </p>
          </div>
          <Button onClick={() => { void load(); }} disabled={loading} variant="outline" size="sm">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {loading && <div className="card text-muted-foreground">Computing your score…</div>}
      {error && !loading && <div className="card text-red-600">{error}</div>}

      {!loading && !error && score && (
        <div className="grid gap-6 lg:grid-cols-3">

          {/* Score ring + breakdown */}
          <FinancialCard variant="financial" className="lg:col-span-1">
            <FinancialCardHeader>
              <FinancialCardTitle>Overall Score</FinancialCardTitle>
              <FinancialCardDescription>Period: {score.period}</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent className="flex flex-col items-center gap-6">
              <ScoreRing score={score.score} grade={score.grade} />

              <div className="w-full space-y-3">
                <MetricBar
                  label="Savings Rate"
                  points={score.breakdown.savings_rate.points}
                  max={score.breakdown.savings_rate.max}
                  colorClass={metricColor(score.breakdown.savings_rate.points, score.breakdown.savings_rate.max)}
                />
                <MetricBar
                  label="Spending Stability"
                  points={score.breakdown.spending_stability.points}
                  max={score.breakdown.spending_stability.max}
                  colorClass={metricColor(score.breakdown.spending_stability.points, score.breakdown.spending_stability.max)}
                />
                <MetricBar
                  label="Bill Reliability"
                  points={score.breakdown.bill_reliability.points}
                  max={score.breakdown.bill_reliability.max}
                  colorClass={metricColor(score.breakdown.bill_reliability.points, score.breakdown.bill_reliability.max)}
                />
                <MetricBar
                  label="Trend"
                  points={score.breakdown.trend.points}
                  max={score.breakdown.trend.max}
                  colorClass={metricColor(score.breakdown.trend.points, score.breakdown.trend.max)}
                />
              </div>
            </FinancialCardContent>
          </FinancialCard>

          {/* Detail cards */}
          <div className="lg:col-span-2 space-y-4">
            {/* Metric detail grid */}
            <div className="grid gap-4 sm:grid-cols-2">

              {/* Savings Rate */}
              <FinancialCard variant="financial">
                <FinancialCardHeader className="pb-2">
                  <FinancialCardTitle className="text-sm">Savings Rate</FinancialCardTitle>
                  <FinancialCardDescription>{score.breakdown.savings_rate.points.toFixed(1)} / 25 pts</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent className="space-y-1 text-sm">
                  {score.breakdown.savings_rate.detail && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Income</span>
                        <span>{Number(score.breakdown.savings_rate.detail['income'] ?? 0).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Expenses</span>
                        <span>{Number(score.breakdown.savings_rate.detail['expenses'] ?? 0).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between font-semibold">
                        <span className="text-muted-foreground">Savings Rate</span>
                        <span>{score.breakdown.savings_rate.detail['savings_rate_pct']}%</span>
                      </div>
                    </>
                  )}
                </FinancialCardContent>
              </FinancialCard>

              {/* Spending Stability */}
              <FinancialCard variant="financial">
                <FinancialCardHeader className="pb-2">
                  <FinancialCardTitle className="text-sm">Spending Stability</FinancialCardTitle>
                  <FinancialCardDescription>{score.breakdown.spending_stability.points.toFixed(1)} / 25 pts</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent className="space-y-1 text-sm">
                  {score.breakdown.spending_stability.detail && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Days with data</span>
                        <span>{score.breakdown.spending_stability.detail['days_with_data'] ?? '—'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Avg daily spend</span>
                        <span>{score.breakdown.spending_stability.detail['mean_daily_spend'] ?? '—'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Variability (CV)</span>
                        <span>{score.breakdown.spending_stability.detail['cv'] != null
                          ? Number(score.breakdown.spending_stability.detail['cv']).toFixed(2)
                          : '—'}</span>
                      </div>
                    </>
                  )}
                </FinancialCardContent>
              </FinancialCard>

              {/* Bill Reliability */}
              <FinancialCard variant="financial">
                <FinancialCardHeader className="pb-2">
                  <FinancialCardTitle className="text-sm">Bill Reliability</FinancialCardTitle>
                  <FinancialCardDescription>{score.breakdown.bill_reliability.points.toFixed(1)} / 25 pts</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent className="space-y-1 text-sm">
                  {score.breakdown.bill_reliability.detail && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Total bills</span>
                        <span>{score.breakdown.bill_reliability.detail['total']}</span>
                      </div>
                      <div className="flex justify-between text-green-600">
                        <span>On time</span>
                        <span>{score.breakdown.bill_reliability.detail['on_time']}</span>
                      </div>
                      <div className="flex justify-between text-red-500">
                        <span>Overdue</span>
                        <span>{score.breakdown.bill_reliability.detail['overdue']}</span>
                      </div>
                    </>
                  )}
                </FinancialCardContent>
              </FinancialCard>

              {/* Trend */}
              <FinancialCard variant="financial">
                <FinancialCardHeader className="pb-2">
                  <FinancialCardTitle className="text-sm">Month-over-Month Trend</FinancialCardTitle>
                  <FinancialCardDescription>{score.breakdown.trend.points.toFixed(1)} / 25 pts</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent className="space-y-1 text-sm">
                  {score.breakdown.trend.detail && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">This month expenses</span>
                        <span>{Number(score.breakdown.trend.detail['current_month_expenses'] ?? 0).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Last month expenses</span>
                        <span>{Number(score.breakdown.trend.detail['previous_month_expenses'] ?? 0).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between font-semibold items-center">
                        <span className="text-muted-foreground">Change</span>
                        <span className="flex items-center gap-1">
                          <TrendIcon changePct={score.breakdown.trend.detail['change_pct'] as number | null} />
                          {score.breakdown.trend.detail['change_pct'] != null
                            ? `${Number(score.breakdown.trend.detail['change_pct']) > 0 ? '+' : ''}${Number(score.breakdown.trend.detail['change_pct']).toFixed(1)}%`
                            : 'No prior data'}
                        </span>
                      </div>
                    </>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            </div>

            {/* History */}
            {history && history.history.length > 0 && (
              <FinancialCard variant="financial">
                <FinancialCardHeader>
                  <FinancialCardTitle>Score History</FinancialCardTitle>
                  <FinancialCardDescription>Last {history.history.length} months</FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <HistoryChart history={history.history} />
                </FinancialCardContent>
              </FinancialCard>
            )}

            {/* Tips */}
            {tips && tips.tips.length > 0 && (
              <FinancialCard variant="financial">
                <FinancialCardHeader>
                  <FinancialCardTitle className="flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-yellow-500" />
                    Actionable Tips
                  </FinancialCardTitle>
                  <FinancialCardDescription>
                    Focused on your lowest-scoring areas
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <ul className="space-y-2">
                    {tips.tips.map((tip, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                        <span className="mt-1 h-2 w-2 flex-shrink-0 rounded-full bg-primary" />
                        {tip}
                      </li>
                    ))}
                  </ul>
                </FinancialCardContent>
              </FinancialCard>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
