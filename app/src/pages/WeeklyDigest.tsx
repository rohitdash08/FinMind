import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/components/ui/use-toast';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Mail,
  Calendar,
  DollarSign,
  BarChart3,
  Lightbulb,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { getWeeklyDigest, sendWeeklyDigestEmail, type WeeklyDigest } from '@/api/insights';

export default function WeeklyDigestPage() {
  const { toast } = useToast();
  const [refDate, setRefDate] = useState<string | undefined>();

  const { data: digest, isLoading } = useQuery<WeeklyDigest>({
    queryKey: ['weekly-digest', refDate],
    queryFn: () => getWeeklyDigest(refDate),
  });

  const sendEmailMutation = useMutation({
    mutationFn: () => sendWeeklyDigestEmail(refDate),
    onSuccess: (data) => {
      toast({
        title: data.sent ? 'Email sent' : 'Email not sent',
        description: data.sent
          ? 'Weekly digest has been sent to your email.'
          : 'Could not send email. Check SMTP settings.',
      });
    },
    onError: (err: Error) => {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    },
  });

  const navigateWeek = (direction: 'prev' | 'next') => {
    const current = refDate ? new Date(refDate) : new Date();
    const offset = direction === 'prev' ? -7 : 7;
    current.setDate(current.getDate() + offset);
    setRefDate(current.toISOString().split('T')[0]);
  };

  const trendIcon = {
    up: <TrendingUp className="h-5 w-5 text-destructive" />,
    down: <TrendingDown className="h-5 w-5 text-green-600" />,
    stable: <Minus className="h-5 w-5 text-muted-foreground" />,
  };

  const trendBadge = {
    up: <Badge variant="destructive">Spending Up</Badge>,
    down: <Badge className="bg-green-100 text-green-800">Spending Down</Badge>,
    stable: <Badge variant="secondary">Stable</Badge>,
  };

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-primary" />
            Weekly Digest
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Your weekly financial summary and insights
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => sendEmailMutation.mutate()}
          disabled={sendEmailMutation.isPending}
        >
          <Mail className="h-4 w-4 mr-2" />
          {sendEmailMutation.isPending ? 'Sending...' : 'Email Digest'}
        </Button>
      </div>

      {/* Week Navigation */}
      <div className="flex items-center justify-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigateWeek('prev')}>
          <ChevronLeft className="h-5 w-5" />
        </Button>
        <span className="text-sm font-medium">
          {digest ? `${digest.period.week_start} — ${digest.period.week_end}` : 'Loading...'}
        </span>
        <Button variant="ghost" size="icon" onClick={() => navigateWeek('next')}>
          <ChevronRight className="h-5 w-5" />
        </Button>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground text-center py-12">Loading digest...</p>
      ) : !digest ? (
        <p className="text-muted-foreground text-center py-12">No data available</p>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <FinancialCard variant="premium">
              <FinancialCardHeader>
                <FinancialCardDescription>Total Expenses</FinancialCardDescription>
                <FinancialCardTitle className="text-2xl">
                  ${digest.summary.total_expenses.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </FinancialCardTitle>
              </FinancialCardHeader>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardDescription>Total Income</FinancialCardDescription>
                <FinancialCardTitle className="text-2xl text-green-600">
                  ${digest.summary.total_income.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </FinancialCardTitle>
              </FinancialCardHeader>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardDescription>Net Flow</FinancialCardDescription>
                <FinancialCardTitle className={`text-2xl ${digest.summary.net_flow >= 0 ? 'text-green-600' : 'text-destructive'}`}>
                  ${digest.summary.net_flow.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </FinancialCardTitle>
              </FinancialCardHeader>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardDescription>Week-over-Week</FinancialCardDescription>
                <div className="flex items-center gap-2 mt-1">
                  {trendIcon[digest.summary.trend]}
                  <FinancialCardTitle className="text-xl">
                    {digest.summary.wow_change_pct > 0 ? '+' : ''}{digest.summary.wow_change_pct}%
                  </FinancialCardTitle>
                </div>
                <div className="mt-1">{trendBadge[digest.summary.trend]}</div>
              </FinancialCardHeader>
            </FinancialCard>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Daily Spending */}
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  Daily Spending
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  {digest.daily_spending.map((day) => {
                    const maxAmount = Math.max(...digest.daily_spending.map((d) => d.amount), 1);
                    const pct = (day.amount / maxAmount) * 100;
                    return (
                      <div key={day.date} className="space-y-1">
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">
                            {new Date(day.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                          </span>
                          <span className="font-medium">${day.amount.toFixed(2)}</span>
                        </div>
                        <Progress value={pct} className="h-2" />
                      </div>
                    );
                  })}
                </div>
              </FinancialCardContent>
            </FinancialCard>

            {/* Top Categories */}
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4" />
                  Top Categories
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                {digest.top_categories.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No expenses this week</p>
                ) : (
                  <div className="space-y-3">
                    {digest.top_categories.map((cat) => (
                      <div key={cat.category_name} className="space-y-1">
                        <div className="flex justify-between text-sm">
                          <span className="font-medium">{cat.category_name}</span>
                          <span>
                            ${cat.amount.toFixed(2)}{' '}
                            <span className="text-muted-foreground">({cat.share_pct}%)</span>
                          </span>
                        </div>
                        <Progress value={cat.share_pct} className="h-2" />
                      </div>
                    ))}
                  </div>
                )}
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* Insights */}
          {digest.insights.length > 0 && (
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Lightbulb className="h-4 w-4 text-yellow-500" />
                  Insights
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-2">
                  {digest.insights.map((insight, i) => (
                    <p key={i} className="text-sm text-muted-foreground">
                      {insight}
                    </p>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}

          {/* Previous Week Comparison */}
          <FinancialCard variant="financial" size="sm">
            <FinancialCardContent>
              <p className="text-sm text-muted-foreground">
                Previous week ({digest.period.prev_week_start} to {digest.period.prev_week_end}):
                expenses ${digest.summary.prev_week_expenses.toFixed(2)}, income ${digest.summary.prev_week_income.toFixed(2)}
              </p>
            </FinancialCardContent>
          </FinancialCard>
        </>
      )}
    </div>
  );
}
