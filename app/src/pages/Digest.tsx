import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import { getWeeklyDigest, sendWeeklyDigest, type WeeklyDigest } from '@/api/digest';
import { formatMoney } from '@/lib/currency';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Mail,
  RefreshCw,
  Lightbulb,
  ArrowUpRight,
  ArrowDownRight,
  Receipt,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';

const trendIcon = (dir: string) => {
  if (dir === 'up') return <TrendingUp className="h-4 w-4 text-red-500" />;
  if (dir === 'down') return <TrendingDown className="h-4 w-4 text-green-500" />;
  return <Minus className="h-4 w-4 text-muted-foreground" />;
};

export default function Digest() {
  const { toast } = useToast();
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await getWeeklyDigest();
      setDigest(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load digest';
      toast({ title: 'Error', description: msg });
    } finally {
      setLoading(false);
    }
  }

  async function handleSend() {
    setSending(true);
    try {
      await sendWeeklyDigest({ email: true });
      toast({ title: 'Digest sent!', description: 'Check your email.' });
    } catch {
      toast({ title: 'Failed to send digest' });
    } finally {
      setSending(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="page-wrap flex items-center justify-center min-h-[40vh]">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!digest) {
    return (
      <div className="page-wrap">
        <p className="text-muted-foreground">Unable to load your weekly digest.</p>
      </div>
    );
  }

  const { summary, trends, category_breakdown, upcoming_bills, ai_insights, period } = digest;

  return (
    <div className="page-wrap space-y-6">
      {/* Header */}
      <div className="page-header">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              {period.start} – {period.end}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => void load()}>
              <RefreshCw className="h-4 w-4 mr-1" /> Refresh
            </Button>
            <Button size="sm" onClick={handleSend} disabled={sending}>
              <Mail className="h-4 w-4 mr-1" /> {sending ? 'Sending…' : 'Email Digest'}
            </Button>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <ArrowUpRight className="h-4 w-4 text-green-500" /> Income
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-2xl font-bold">{formatMoney(summary.total_income)}</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <ArrowDownRight className="h-4 w-4 text-red-500" /> Expenses
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-2xl font-bold">{formatMoney(summary.total_expenses)}</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              {trendIcon(summary.net_flow >= 0 ? 'down' : 'up')} Net Flow
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className={`text-2xl font-bold ${summary.net_flow >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {formatMoney(summary.net_flow)}
            </p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Trends */}
      <FinancialCard>
        <FinancialCardHeader>
          <FinancialCardTitle className="flex items-center gap-2">
            {trendIcon(trends.direction)} Week-over-Week Trend
          </FinancialCardTitle>
          <FinancialCardDescription>
            Spending is <strong>{trends.direction}</strong> by{' '}
            <strong>{Math.abs(trends.spending_change_pct).toFixed(1)}%</strong> compared to last week
          </FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="flex gap-8 text-sm text-muted-foreground">
            <span>This week: {formatMoney(trends.current_week_total)}</span>
            <span>Last week: {formatMoney(trends.previous_week_total)}</span>
          </div>
        </FinancialCardContent>
      </FinancialCard>

      {/* Category Breakdown */}
      {category_breakdown.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>Spending by Category</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-3">
              {category_breakdown.map((cat) => {
                const pct =
                  summary.total_expenses > 0
                    ? ((cat.total / summary.total_expenses) * 100).toFixed(1)
                    : '0';
                return (
                  <div key={cat.category_id ?? 'uncat'} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{cat.category_name}</span>
                      <Badge variant="secondary">{pct}%</Badge>
                    </div>
                    <span className="font-semibold">{formatMoney(cat.total)}</span>
                  </div>
                );
              })}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Upcoming Bills */}
      {upcoming_bills.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Receipt className="h-4 w-4" /> Upcoming Bills
            </FinancialCardTitle>
            <FinancialCardDescription>
              Total due: {formatMoney(digest.upcoming_bills_total)}
            </FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-2">
              {upcoming_bills.map((bill) => (
                <div key={bill.id} className="flex items-center justify-between text-sm">
                  <div>
                    <span className="font-medium">{bill.name}</span>
                    <span className="text-muted-foreground ml-2">due {bill.next_due_date}</span>
                  </div>
                  <span className="font-semibold">{formatMoney(bill.amount)}</span>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* AI Insights */}
      {ai_insights && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-yellow-500" /> AI Insights
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <ul className="space-y-2">
              {ai_insights.highlights.map((h, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-primary mt-0.5">•</span>
                  <span>{h}</span>
                </li>
              ))}
            </ul>
            {ai_insights.tip && (
              <div className="mt-4 p-3 rounded-lg bg-primary/5 border border-primary/10 text-sm">
                💡 <strong>Tip:</strong> {ai_insights.tip}
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>
      )}
    </div>
  );
}
