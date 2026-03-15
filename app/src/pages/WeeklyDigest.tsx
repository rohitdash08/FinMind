import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  ArrowDownRight,
  ArrowUpRight,
  TrendingUp,
  Wallet,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigest } from '@/api/insights';
import { listCategories, type Category } from '@/api/categories';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

export function WeeklyDigestPage() {
  const [data, setData] = useState<WeeklyDigest | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [digest, cats] = await Promise.all([
          getWeeklyDigest({ offset }),
          listCategories(),
        ]);
        setData(digest);
        setCategories(cats);
      } catch (err: any) {
        setError(err.message || 'Failed to load weekly digest');
      } finally {
        setLoading(false);
      }
    })();
  }, [offset]);

  const categoryMap = categories.reduce((acc, cat) => {
    acc[cat.id.toString()] = cat.name;
    return acc;
  }, {} as Record<string, string>);

  const sortedCategories = data ? Object.entries(data.category_breakdown).sort((a, b) => b[1] - a[1]) : [];

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Weekly Smart Digest</h1>
            <p className="page-subtitle">
              {data ? `${data.week_start} to ${data.week_end}` : 'Loading...'}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setOffset(offset - 1)}>
              <ChevronLeft className="w-4 h-4 mr-1" /> Previous
            </Button>
            <Button variant="outline" size="sm" onClick={() => setOffset(0)} disabled={offset === 0}>
              Current
            </Button>
            <Button variant="outline" size="sm" onClick={() => setOffset(offset + 1)} disabled={offset >= 0}>
              Next <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Spent</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{loading ? '...' : currency(data?.total_spent || 0)}</div>
            <div className="flex items-center text-sm">
              {data && data.wow_change_pct > 0 ? (
                <ArrowUpRight className="w-4 h-4 text-destructive mr-1" />
              ) : (
                <ArrowDownRight className="w-4 h-4 text-success mr-1" />
              )}
              <span className={data && data.wow_change_pct > 0 ? 'text-destructive font-medium' : 'text-success font-medium'}>
                {data ? `${Math.abs(data.wow_change_pct).toFixed(1)}%` : '0%'}
              </span>
              <span className="text-muted-foreground ml-2">vs last week</span>
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="fade-in-up" style={{ animationDelay: '0.1s' }}>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Income</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{loading ? '...' : currency(data?.total_income || 0)}</div>
            <div className="text-xs text-muted-foreground flex items-center">
              <TrendingUp className="w-3 h-3 mr-1" /> Inflow tracked
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="fade-in-up" style={{ animationDelay: '0.2s' }}>
          <FinancialCardHeader className="pb-2">
            <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Net Flow</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className={`metric-value mb-1 ${data && data.net_flow >= 0 ? 'text-success' : 'text-destructive'}`}>
              {loading ? '...' : currency(data?.net_flow || 0)}
            </div>
            <div className="text-xs text-muted-foreground flex items-center">
              <Wallet className="w-3 h-3 mr-1" /> Cash balance change
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <div className="grid lg:grid-cols-2 gap-8">
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader>
            <FinancialCardTitle className="section-title flex items-center">
              <Sparkles className="w-5 h-5 mr-2 text-primary" />
              AI Financial Insights
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {loading ? (
              <div className="space-y-4">
                <div className="h-4 bg-muted animate-pulse rounded w-3/4" />
                <div className="h-4 bg-muted animate-pulse rounded w-5/6" />
                <div className="h-4 bg-muted animate-pulse rounded w-2/3" />
              </div>
            ) : (
              <ul className="space-y-4">
                {data?.insights.map((insight, i) => (
                  <li key={i} className="flex items-start gap-3 text-foreground bg-primary-light/10 p-3 rounded-lg border border-primary-light/20">
                    <div className="mt-1 w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
                    <span>{insight}</span>
                  </li>
                ))}
                {data?.insights.length === 0 && <li className="text-muted-foreground">No specific insights for this period.</li>}
              </ul>
            )}
            {data?.method === 'gemini' && (
              <p className="text-[10px] text-muted-foreground mt-4 text-right">Powered by Gemini AI</p>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader>
            <FinancialCardTitle className="section-title">Category Breakdown</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => <div key={i} className="h-8 bg-muted animate-pulse rounded" />)}
              </div>
            ) : sortedCategories.length === 0 ? (
              <div className="text-sm text-muted-foreground">No data recorded.</div>
            ) : (
              <div className="space-y-4">
                {sortedCategories.map(([id, amount]) => {
                  const share = data ? (amount / data.total_spent) * 100 : 0;
                  return (
                    <div key={id} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{categoryMap[id] || 'Uncategorized'}</span>
                        <span className="text-muted-foreground">{currency(amount)} ({share.toFixed(0)}%)</span>
                      </div>
                      <div className="chart-track h-2 bg-muted rounded-full overflow-hidden">
                        <div 
                          className="chart-fill-primary h-full bg-primary" 
                          style={{ width: `${Math.max(2, Math.min(100, share))}%` }} 
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>
      </div>
    </div>
  );
}
