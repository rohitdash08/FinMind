import { useQuery } from '@tanstack/react-query';
import { fetchWeeklyDigest, type WeeklyDigest } from '@/api/digest';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Lightbulb, Calendar } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';

export default function Digest() {
  const [week, setWeek] = useState<string | undefined>(undefined);

  const { data, isLoading, error } = useQuery<WeeklyDigest>({
    queryKey: ['weekly-digest', week],
    queryFn: () => fetchWeeklyDigest(week),
  });

  const navigateWeek = (direction: -1 | 1) => {
    const current = data?.week;
    if (!current) return;
    const match = current.match(/^(\d{4})-W(\d{2})$/);
    if (!match) return;
    let y = parseInt(match[1]);
    let w = parseInt(match[2]) + direction;
    if (w < 1) { y--; w = 52; }
    if (w > 52) { y++; w = 1; }
    setWeek(`${y}-W${String(w).padStart(2, '0')}`);
  };

  if (isLoading) {
    return (
      <div className="container-financial py-8">
        <div className="flex items-center justify-center h-64 text-muted-foreground">Loading digest…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container-financial py-8">
        <div className="flex items-center justify-center h-64 text-destructive">Failed to load digest.</div>
      </div>
    );
  }

  if (!data) return null;

  const categories = Object.entries(data.category_breakdown);
  const totalSpent = data.total_spent;
  const maxCat = categories.length > 0 ? Math.max(...categories.map(([, v]) => v)) : 1;

  return (
    <div className="container-financial py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Weekly Digest</h1>
          <p className="text-sm text-muted-foreground">
            {data.period.start} — {data.period.end}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigateWeek(-1)}>← Prev</Button>
          <Badge variant="secondary" className="text-sm font-mono">{data.week}</Badge>
          <Button variant="outline" size="sm" onClick={() => navigateWeek(1)}>Next →</Button>
        </div>
      </div>

      {/* Total Spent Card */}
      <FinancialCard>
        <FinancialCardHeader>
          <FinancialCardTitle className="flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-primary" />
            Total Spent
          </FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          <p className="text-3xl font-bold">{totalSpent.toFixed(2)}</p>
        </FinancialCardContent>
      </FinancialCard>

      {/* Category Breakdown */}
      <FinancialCard>
        <FinancialCardHeader>
          <FinancialCardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            Category Breakdown
          </FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          {categories.length === 0 ? (
            <p className="text-muted-foreground text-sm">No expenses this week.</p>
          ) : (
            <div className="space-y-3">
              {categories
                .sort((a, b) => b[1] - a[1])
                .map(([name, amount]) => {
                  const pct = totalSpent > 0 ? ((amount / totalSpent) * 100).toFixed(1) : '0';
                  const wow = data.week_over_week_change[name];
                  return (
                    <div key={name} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{name}</span>
                        <div className="flex items-center gap-2">
                          <span>{amount.toFixed(2)} ({pct}%)</span>
                          {wow && wow.change !== 0 && (
                            <Badge variant={wow.change > 0 ? 'destructive' : 'default'} className="text-xs">
                              {wow.change > 0 ? <TrendingUp className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                              {wow.change > 0 ? '+' : ''}{wow.change_pct}%
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${(amount / maxCat) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>

      {/* Trends */}
      {data.trends.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-primary" />
              Trends
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <ul className="space-y-2">
              {data.trends.map((t, i) => (
                <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                  <Calendar className="h-4 w-4 mt-0.5 text-primary shrink-0" />
                  {t}
                </li>
              ))}
            </ul>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Insights */}
      {data.insights.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5 text-warning" />
              Insights
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <ul className="space-y-2">
              {data.insights.map((insight, i) => (
                <li key={i} className="text-sm text-muted-foreground">{insight}</li>
              ))}
            </ul>
          </FinancialCardContent>
        </FinancialCard>
      )}
    </div>
  );
}
