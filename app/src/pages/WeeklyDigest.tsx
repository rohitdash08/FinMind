/**
 * 每周财务摘要页面
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  ArrowDownRight,
  ArrowUpRight,
  Calendar,
  Mail,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
  Lightbulb,
  AlertTriangle,
  CheckCircle,
  Loader2,
} from 'lucide-react';
import { getWeeklySummary, type WeeklyDigestSummary } from '@/api/weeklyDigest';
import { formatMoney } from '@/lib/currency';
import { useToast } from '@/hooks/use-toast';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

function getCurrentWeekStart(): string {
  const today = new Date();
  const daysSinceMonday = today.getDay() === 0 ? 6 : today.getDay() - 1;
  const monday = new Date(today);
  monday.setDate(today.getDate() - daysSinceMonday);
  return monday.toISOString().slice(0, 10);
}

export function WeeklyDigest() {
  const { toast } = useToast();
  const [summary, setSummary] = useState<WeeklyDigestSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [weekStart, setWeekStart] = useState(getCurrentWeekStart());
  const [sendingEmail, setSendingEmail] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getWeeklySummary(weekStart);
        setSummary(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load weekly summary');
      } finally {
        setLoading(false);
      }
    })();
  }, [weekStart]);

  const handleSendEmail = async () => {
    setSendingEmail(true);
    try {
      // TODO: 实现邮件发送 API 调用
      // await sendSummaryEmail(weekStart);
      toast({
        title: 'Email feature coming soon!',
        description: 'Weekly digest emails will be available in the next release.',
      });
    } catch (err: unknown) {
      toast({
        title: 'Failed to send email',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setSendingEmail(false);
    }
  };

  const handlePrevWeek = () => {
    const current = new Date(weekStart);
    current.setDate(current.getDate() - 7);
    setWeekStart(current.toISOString().slice(0, 10));
  };

  const handleNextWeek = () => {
    const current = new Date(weekStart);
    current.setDate(current.getDate() + 7);
    // 不能超过本周
    if (current <= new Date()) {
      setWeekStart(current.toISOString().slice(0, 10));
    }
  };

  const summaryCards = useMemo(() => {
    if (!summary) return [];

    const { week_data, comparison } = summary;
    return [
      {
        title: 'Net Flow',
        amount: currency(week_data.net_flow),
        change: `${comparison.net_flow_pct_change >= 0 ? '+' : ''}${comparison.net_flow_pct_change}% vs last week`,
        trend: comparison.net_flow_pct_change >= 0 ? 'up' : 'down',
        icon: Wallet,
        description: `Week of ${weekStart}`,
      },
      {
        title: 'Income',
        amount: currency(week_data.total_income),
        change: `${comparison.total_income_pct_change >= 0 ? '+' : ''}${comparison.total_income_pct_change}% vs last week`,
        trend: comparison.total_income_pct_change >= 0 ? 'up' : 'down',
        icon: TrendingUp,
        description: 'This week',
      },
      {
        title: 'Expenses',
        amount: currency(week_data.total_expenses),
        change: `${comparison.total_expenses_pct_change >= 0 ? '+' : ''}${comparison.total_expenses_pct_change}% vs last week`,
        trend: comparison.total_expenses_pct_change >= 0 ? 'up' : 'down',
        icon: TrendingDown,
        description: 'This week',
      },
      {
        title: 'Transactions',
        amount: week_data.transaction_count.toString(),
        change: 'Total entries',
        trend: 'neutral' as const,
        icon: Calendar,
        description: 'This week',
      },
    ];
  }, [summary, weekStart]);

  if (loading) {
    return (
      <div className="page-wrap flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="page-wrap">
        <div className="text-center py-12">
          <AlertTriangle className="w-12 h-12 mx-auto text-destructive mb-4" />
          <h3 className="text-lg font-semibold mb-2">Failed to load weekly digest</h3>
          <p className="text-muted-foreground mb-4">{error || 'No data available'}</p>
          <Button onClick={() => window.location.reload()}>Try Again</Button>
        </div>
      </div>
    );
  }

  const { week_data, upcoming_bills = [] } = summary.week_data;
  const topCategories = Object.entries(week_data.categories || {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <div className="page-wrap space-y-6">
      {/* 页面标题和导航 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-primary" />
            Weekly Financial Digest
          </h1>
          <p className="text-muted-foreground">
            Your AI-powered financial insights for the week of {weekStart}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handlePrevWeek}>
            <ArrowDownRight className="w-4 h-4 -rotate-90 mr-1" />
            Previous
          </Button>
          <Button variant="outline" size="sm" onClick={handleNextWeek}>
            Next
            <ArrowUpRight className="w-4 h-4 rotate-90 ml-1" />
          </Button>
          <Button variant="default" size="sm" onClick={handleSendEmail} disabled={sendingEmail}>
            {sendingEmail ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Mail className="w-4 h-4 mr-2" />}
            Email Me
          </Button>
        </div>
      </div>

      {/* 摘要卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {summaryCards.map((card, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <card.icon className="w-4 h-4" />
                {card.title}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{card.amount}</div>
              <p className={`text-xs flex items-center mt-1 ${
                card.trend === 'up' ? 'text-green-600' :
                card.trend === 'down' ? 'text-red-600' :
                'text-muted-foreground'
              }`}>
                {card.trend === 'up' ? <TrendingUp className="w-3 h-3 mr-1" /> :
                 card.trend === 'down' ? <TrendingDown className="w-3 h-3 mr-1" /> : null}
                {card.change}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* AI 摘要内容 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 主要亮点 */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              This Week in Review
            </CardTitle>
            <CardDescription>
              AI-powered insights for {weekStart} to {summary.week_end}
              <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-secondary">
                {summary.method === 'gemini' ? '✨ AI Generated' : '📊 Heuristic'}
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Highlights */}
            <div>
              <h3 className="font-semibold mb-3 flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-600" />
                Highlights
              </h3>
              <ul className="space-y-2">
                {summary.highlights.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-green-600 mt-1">✓</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* Insights */}
            <div>
              <h3 className="font-semibold mb-3 flex items-center gap-2">
                <Lightbulb className="w-5 h-5 text-yellow-600" />
                Insights
              </h3>
              <ul className="space-y-2">
                {summary.insights.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-yellow-600 mt-1">💡</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* Warnings */}
            {summary.warnings && summary.warnings.length > 0 && (
              <div>
                <h3 className="font-semibold mb-3 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-orange-600" />
                  Watch Outs
                </h3>
                <ul className="space-y-2">
                  {summary.warnings.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <span className="text-orange-600 mt-1">⚠️</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Tips */}
            <div>
              <h3 className="font-semibold mb-3 flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-blue-600" />
                Pro Tips for Next Week
              </h3>
              <ul className="space-y-2">
                {summary.tips.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-blue-600 mt-1">→</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
          <CardFooter className="border-t pt-4 text-sm text-muted-foreground">
            💬 {summary.closing}
          </CardFooter>
        </Card>

        {/* 支出类别和账单 */}
        <div className="space-y-6">
          {/* 支出类别 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Spending by Category</CardTitle>
              <CardDescription>Top 5 categories this week</CardDescription>
            </CardHeader>
            <CardContent>
              {topCategories.length > 0 ? (
                <div className="space-y-3">
                  {topCategories.map(([catId, amount], i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">
                          {catId === 'uncategorized' ? 'Uncategorized' : `Category ${catId}`}
                        </span>
                        <span>{currency(amount)}</span>
                      </div>
                      <div className="w-full h-2 bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{
                            width: `${Math.min(100, (amount / (topCategories[0][1] || 1)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No spending data this week
                </p>
              )}
            </CardContent>
          </Card>

          {/* 即将到期的账单 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Upcoming Bills</CardTitle>
              <CardDescription>Due this week</CardDescription>
            </CardHeader>
            <CardContent>
              {upcoming_bills.length > 0 ? (
                <div className="space-y-2">
                  {upcoming_bills.map((bill, i) => (
                    <div key={i} className="flex justify-between items-center py-2 border-b last:border-0">
                      <div>
                        <div className="font-medium text-sm">{bill.name}</div>
                        <div className="text-xs text-muted-foreground">Due: {bill.due_date}</div>
                      </div>
                      <div className="font-semibold">{currency(bill.amount)}</div>
                    </div>
                  ))}
                  <div className="pt-2 border-t flex justify-between font-semibold text-sm">
                    <span>Total</span>
                    <span>
                      {currency(upcoming_bills.reduce((s, b) => s + b.amount, 0))}
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No bills due this week 🎉
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
