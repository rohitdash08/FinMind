import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import { formatMoney } from '@/lib/currency';
import {
  getWeeklyDigest,
  getSpendingTrends,
  type WeeklyDigest as WeeklyDigestType,
  type SpendingTrends as SpendingTrendsType,
} from '@/api/digest';
import {
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Calendar,
  Lightbulb,
  BarChart3,
  Sparkles,
} from 'lucide-react';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import {
  Bar,
  BarChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Cell,
  Pie,
  PieChart,
} from 'recharts';

const CATEGORY_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
  '#8884d8',
  '#82ca9d',
  '#ffc658',
];

function formatWeekRange(start: string, end: string): string {
  const s = new Date(start + 'T00:00:00');
  const e = new Date(end + 'T00:00:00');
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  const yearOpts: Intl.DateTimeFormatOptions = { ...opts, year: 'numeric' };
  if (s.getFullYear() !== e.getFullYear()) {
    return `${s.toLocaleDateString(undefined, yearOpts)} – ${e.toLocaleDateString(undefined, yearOpts)}`;
  }
  return `${s.toLocaleDateString(undefined, opts)} – ${e.toLocaleDateString(undefined, yearOpts)}`;
}

function TrendIcon({ pct }: { pct: number | null }) {
  if (pct === null) return <Minus className="h-4 w-4 text-muted-foreground" />;
  if (pct > 5) return <TrendingUp className="h-4 w-4 text-destructive" />;
  if (pct < -5) return <TrendingDown className="h-4 w-4 text-emerald-600" />;
  return <Minus className="h-4 w-4 text-muted-foreground" />;
}

function TrendBadge({ trend }: { trend: string }) {
  const config: Record<string, { icon: typeof TrendingUp; color: string; label: string }> = {
    increasing: { icon: TrendingUp, color: 'text-destructive', label: 'Increasing' },
    decreasing: { icon: TrendingDown, color: 'text-emerald-600', label: 'Decreasing' },
    stable: { icon: Minus, color: 'text-muted-foreground', label: 'Stable' },
  };
  const c = config[trend] || config.stable;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${c.color}`}>
      <Icon className="h-3 w-3" />
      {c.label}
    </span>
  );
}

export default function Digest() {
  const { toast } = useToast();
  const [weekOffset, setWeekOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [trendsLoading, setTrendsLoading] = useState(true);
  const [digest, setDigest] = useState<WeeklyDigestType | null>(null);
  const [trends, setTrends] = useState<SpendingTrendsType | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadDigest(offset: number) {
    setLoading(true);
    setError(null);
    try {
      const data = await getWeeklyDigest({ weekOffset: offset });
      setDigest(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load digest';
      setError(msg);
      toast({ title: 'Failed to load digest', description: msg });
    } finally {
      setLoading(false);
    }
  }

  async function loadTrends() {
    setTrendsLoading(true);
    try {
      const data = await getSpendingTrends({ weeks: 8 });
      setTrends(data);
    } catch {
      // Trends are supplementary — don't block the page
    } finally {
      setTrendsLoading(false);
    }
  }

  useEffect(() => {
    void loadDigest(weekOffset);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekOffset]);

  useEffect(() => {
    void loadTrends();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const categoryChartConfig = useMemo<ChartConfig>(() => {
    if (!digest) return {};
    const config: ChartConfig = {};
    digest.categories.forEach((cat, i) => {
      config[cat.category_name] = {
        label: cat.category_name,
        color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
      };
    });
    return config;
  }, [digest]);

  const trendChartConfig: ChartConfig = {
    total_spent: { label: 'Spending', color: 'hsl(var(--chart-1))' },
    total_income: { label: 'Income', color: 'hsl(var(--chart-2))' },
  };

  const canGoNext = weekOffset < 0;

  return (
    <div className="page-wrap space-y-6">
      {/* Header */}
      <div className="page-header">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="page-title flex items-center gap-2">
              <Sparkles className="h-6 w-6 text-primary" />
              Smart Digest
            </h1>
            <p className="page-subtitle">
              Weekly spending summary with trends and insights.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setWeekOffset((o) => o - 1)}
              disabled={loading || weekOffset <= -51}
            >
              <ChevronLeft className="h-4 w-4" />
              Prev Week
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setWeekOffset(0)}
              disabled={loading || weekOffset === 0}
            >
              This Week
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setWeekOffset((o) => o + 1)}
              disabled={loading || !canGoNext}
            >
              Next Week
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <FinancialCard key={i} variant="financial">
              <FinancialCardContent className="h-24 animate-pulse bg-muted/50 rounded-lg" />
            </FinancialCard>
          ))}
        </div>
      ) : error ? (
        <FinancialCard variant="destructive">
          <FinancialCardContent className="text-center py-8">
            <p className="font-medium">Failed to load digest</p>
            <p className="text-sm mt-1">{error}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => void loadDigest(weekOffset)}
            >
              Retry
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      ) : digest ? (
        <>
          {/* Period Label */}
          <div className="text-center">
            <span className="inline-flex items-center gap-2 rounded-full bg-secondary px-4 py-1 text-sm font-medium text-secondary-foreground">
              <Calendar className="h-4 w-4" />
              {formatWeekRange(digest.period.start, digest.period.end)}
            </span>
          </div>

          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-4">
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm text-muted-foreground">
                  Total Spent
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">
                  {formatMoney(digest.summary.total_spent)}
                </div>
                <div className="flex items-center gap-1 mt-1 text-sm">
                  <TrendIcon pct={digest.summary.wow_change_pct} />
                  <span className={
                    digest.summary.wow_change_pct === null
                      ? 'text-muted-foreground'
                      : digest.summary.wow_change_pct > 0
                        ? 'text-destructive'
                        : 'text-emerald-600'
                  }>
                    {digest.summary.wow_change_pct !== null
                      ? `${digest.summary.wow_change_pct > 0 ? '+' : ''}${digest.summary.wow_change_pct.toFixed(1)}% vs last week`
                      : 'No previous data'}
                  </span>
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm text-muted-foreground">
                  Net Flow
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className={`text-2xl font-bold ${digest.summary.net_flow >= 0 ? 'text-emerald-600' : 'text-destructive'}`}>
                  {digest.summary.net_flow >= 0 ? '+' : ''}
                  {formatMoney(digest.summary.net_flow)}
                </div>
                <div className="text-sm text-muted-foreground mt-1">
                  Income: {formatMoney(digest.summary.total_income)}
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm text-muted-foreground">
                  Daily Average
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">
                  {formatMoney(digest.summary.daily_average)}
                </div>
                <div className="text-sm text-muted-foreground mt-1">
                  {digest.summary.transaction_count} transactions
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm text-muted-foreground">
                  Top Category
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {digest.categories.length > 0 ? (
                  <>
                    <div className="text-2xl font-bold">
                      {digest.categories[0].category_name}
                    </div>
                    <div className="text-sm text-muted-foreground mt-1">
                      {formatMoney(digest.categories[0].amount)} ({digest.categories[0].share_pct}%)
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-muted-foreground">No spending this week</div>
                )}
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* AI Narrative */}
          <FinancialCard variant="premium">
            <FinancialCardHeader>
              <FinancialCardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" />
                Weekly Insights
              </FinancialCardTitle>
              <FinancialCardDescription>
                {digest.narrative_method === 'ai' ? 'AI-powered analysis' : 'Automated analysis'}
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-sm leading-relaxed">{digest.narrative}</p>
            </FinancialCardContent>
          </FinancialCard>

          {/* Category Breakdown + Pie Chart */}
          <div className="grid gap-4 md:grid-cols-2">
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" />
                  Spending by Category
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {digest.categories.length > 0 ? (
                  <ChartContainer config={categoryChartConfig} className="h-[300px] w-full">
                    <BarChart
                      data={digest.categories}
                      layout="vertical"
                      margin={{ left: 20, right: 20, top: 5, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" tickFormatter={(v: number) => formatMoney(v)} />
                      <YAxis
                        type="category"
                        dataKey="category_name"
                        width={100}
                        tick={{ fontSize: 12 }}
                      />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Bar dataKey="amount" radius={[0, 4, 4, 0]}>
                        {digest.categories.map((_, i) => (
                          <Cell
                            key={i}
                            fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ChartContainer>
                ) : (
                  <div className="flex items-center justify-center h-[200px] text-muted-foreground text-sm">
                    No spending data for this week
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Category Distribution</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {digest.categories.length > 0 ? (
                  <ChartContainer config={categoryChartConfig} className="h-[300px] w-full">
                    <PieChart>
                      <Pie
                        data={digest.categories}
                        dataKey="amount"
                        nameKey="category_name"
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        label={({ category_name, share_pct }: { category_name: string; share_pct: number }) =>
                          `${category_name} ${share_pct}%`
                        }
                      >
                        {digest.categories.map((_, i) => (
                          <Cell
                            key={i}
                            fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <ChartTooltip content={<ChartTooltipContent />} />
                    </PieChart>
                  </ChartContainer>
                ) : (
                  <div className="flex items-center justify-center h-[200px] text-muted-foreground text-sm">
                    No spending data for this week
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* Spending Spikes */}
          {digest.spikes.length > 0 && (
            <FinancialCard variant="warning">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5" />
                  Spending Spikes
                </FinancialCardTitle>
                <FinancialCardDescription>
                  Categories with unusual spending increases
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  {digest.spikes.map((spike) => (
                    <div
                      key={spike.category_name}
                      className="flex items-center justify-between rounded-lg border p-3"
                    >
                      <div>
                        <div className="font-medium">{spike.category_name}</div>
                        <div className="text-sm text-muted-foreground">
                          {formatMoney(spike.previous_amount)} → {formatMoney(spike.current_amount)}
                        </div>
                      </div>
                      <div className="text-right">
                        {spike.increase_pct !== null ? (
                          <span className="text-sm font-semibold text-destructive">
                            +{spike.increase_pct.toFixed(0)}%
                          </span>
                        ) : (
                          <span className="text-sm font-medium text-amber-600">New</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {/* Savings Opportunities */}
          {digest.savings_opportunities.length > 0 && (
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Lightbulb className="h-5 w-5 text-amber-500" />
                  Savings Opportunities
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="space-y-2">
                  {digest.savings_opportunities.map((tip, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                        {i + 1}
                      </span>
                      {tip}
                    </li>
                  ))}
                </ul>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {/* Week-over-Week Trend (from trends endpoint) */}
          {!trendsLoading && trends && trends.weekly_totals.length > 0 && (
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  Spending Trend ({trends.weeks_included} Weeks)
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ChartContainer config={trendChartConfig} className="h-[250px] w-full">
                  <LineChart
                    data={trends.weekly_totals}
                    margin={{ left: 20, right: 20, top: 5, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="week_start"
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v: string) => {
                        const d = new Date(v + 'T00:00:00');
                        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                      }}
                    />
                    <YAxis tickFormatter={(v: number) => formatMoney(v)} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Line
                      type="monotone"
                      dataKey="total_spent"
                      stroke="hsl(var(--chart-1))"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      name="Spending"
                    />
                    <Line
                      type="monotone"
                      dataKey="total_income"
                      stroke="hsl(var(--chart-2))"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      name="Income"
                    />
                  </LineChart>
                </ChartContainer>

                {/* Category trends table */}
                {trends.category_trends.length > 0 && (
                  <div className="mt-6">
                    <h4 className="text-sm font-semibold mb-3">Category Trends</h4>
                    <div className="space-y-2">
                      {trends.category_trends.slice(0, 6).map((cat) => (
                        <div
                          key={cat.category_name}
                          className="flex items-center justify-between rounded-lg border p-3"
                        >
                          <div>
                            <div className="font-medium text-sm">{cat.category_name}</div>
                            <div className="text-xs text-muted-foreground">
                              Avg: {formatMoney(cat.average)} / week
                            </div>
                          </div>
                          <TrendBadge trend={cat.trend} />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>
          )}

          {/* Bills Section */}
          {(digest.bills.overdue.length > 0 || digest.bills.upcoming.length > 0) && (
            <FinancialCard variant={digest.bills.overdue.length > 0 ? 'destructive' : 'financial'}>
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5" />
                  Bills
                </FinancialCardTitle>
                <FinancialCardDescription>
                  {digest.bills.overdue.length > 0 && (
                    <span className="text-destructive font-medium">
                      {digest.bills.overdue.length} overdue • {' '}
                    </span>
                  )}
                  {digest.bills.upcoming.length} upcoming in next 14 days
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-2">
                  {digest.bills.overdue.map((bill) => (
                    <div
                      key={`overdue-${bill.id}`}
                      className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 p-3"
                    >
                      <div>
                        <div className="font-medium text-sm">{bill.name}</div>
                        <div className="text-xs text-destructive">
                          {bill.days_overdue} day{bill.days_overdue !== 1 ? 's' : ''} overdue
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-destructive">
                        {formatMoney(bill.amount)}
                      </div>
                    </div>
                  ))}
                  {digest.bills.upcoming.map((bill) => (
                    <div
                      key={`upcoming-${bill.id}`}
                      className="flex items-center justify-between rounded-lg border p-3"
                    >
                      <div>
                        <div className="font-medium text-sm">{bill.name}</div>
                        <div className="text-xs text-muted-foreground">
                          Due in {bill.days_until_due} day{bill.days_until_due !== 1 ? 's' : ''}
                          {bill.autopay_enabled && ' • Autopay'}
                        </div>
                      </div>
                      <div className="text-sm font-semibold">
                        {formatMoney(bill.amount)}
                      </div>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}
        </>
      ) : null}
    </div>
  );
}
