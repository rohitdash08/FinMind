import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import { getWeeklyDigest, type WeeklyDigest as WeeklyDigestType } from '@/api/insights';
import { formatMoney } from '@/lib/currency';
import { TrendingDown, TrendingUp, Info, ArrowLeft, ArrowRight } from 'lucide-react';

export function WeeklyDigest() {
  const { toast } = useToast();
  const [week, setWeek] = useState(() => {
    const now = new Date();
    const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
    return `${d.getUTCFullYear()}-W${weekNo.toString().padStart(2, '0')}`;
  });
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<WeeklyDigestType | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await getWeeklyDigest(week);
      setData(payload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load weekly digest';
      setError(message);
      toast({ title: 'Failed to load weekly digest', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [week]);

  const changeWeek = (offset: number) => {
    const [yearPart, weekPart] = week.split('-W');
    let y = parseInt(yearPart);
    let w = parseInt(weekPart) + offset;
    
    if (w < 1) {
        y -= 1;
        w = 52; // Simplification
    } else if (w > 52) {
        y += 1;
        w = 1;
    }
    setWeek(`${y}-W${w.toString().padStart(2, '0')}`);
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              Your financial health at a glance, delivered weekly.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={() => changeWeek(-1)}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="flex flex-col">
              <Label htmlFor="digest-week" className="sr-only">Week</Label>
              <div className="font-bold px-4">{week}</div>
            </div>
            <Button variant="outline" size="icon" onClick={() => changeWeek(1)}>
              <ArrowRight className="h-4 w-4" />
            </Button>
            <Button onClick={load} disabled={loading} size="sm" className="ml-2">
              Refresh
            </Button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="card">Loading weekly digest...</div>
      ) : error ? (
        <div className="card text-red-600">{error}</div>
      ) : data ? (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-4">
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Total Spent</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{formatMoney(data.total_spent)}</span>
                  {data.week_over_week_change_pct !== 0 && (
                    <div className={`flex items-center text-xs ${data.week_over_week_change_pct > 0 ? 'text-red-500' : 'text-green-500'}`}>
                      {data.week_over_week_change_pct > 0 ? <TrendingUp className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                      {Math.abs(data.week_over_week_change_pct).toFixed(1)}%
                    </div>
                  )}
                </div>
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Total Income</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold text-green-600">{formatMoney(data.total_income)}</div>
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Net Flow</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className={`text-2xl font-bold ${data.net_flow >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {formatMoney(data.net_flow)}
                </div>
              </FinancialCardContent>
            </FinancialCard>
            <FinancialCard variant="financial">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm">Transactions</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">{data.transaction_count}</div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Insights</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <ul className="space-y-3">
                  {data.insights.map((insight, idx) => (
                    <li key={idx} className="flex gap-2 text-sm">
                      <Info className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                      <span>{insight}</span>
                    </li>
                  ))}
                  {data.insights.length === 0 && (
                    <li className="text-muted-foreground italic">No specific insights for this week.</li>
                  )}
                </ul>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial">
              <FinancialCardHeader>
                <FinancialCardTitle>Category Breakdown</FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-4">
                  {data.category_breakdown.map((cat) => (
                    <div key={cat.category_name} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">{cat.category_name}</span>
                        <div className="flex items-center gap-2">
                          <span className="font-bold">{formatMoney(cat.amount)}</span>
                          {cat.wow_change_pct !== null && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${cat.wow_change_pct > 0 ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'}`}>
                              {cat.wow_change_pct > 0 ? '+' : ''}{cat.wow_change_pct.toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-primary" 
                          style={{ width: `${Math.min(100, (cat.amount / data.total_spent) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                  {data.category_breakdown.length === 0 && (
                    <div className="text-center py-4 text-muted-foreground">No spending recorded.</div>
                  )}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle>Top Expenses</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="text-left py-2 font-medium">Date</th>
                      <th className="text-left py-2 font-medium">Notes</th>
                      <th className="text-right py-2 font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {data.top_expenses.map((exp) => (
                      <tr key={exp.id}>
                        <td className="py-2 text-muted-foreground">{new Date(exp.date).toLocaleDateString()}</td>
                        <td className="py-2">{exp.notes || 'No description'}</td>
                        <td className="py-2 text-right font-bold">{formatMoney(exp.amount)}</td>
                      </tr>
                    ))}
                    {data.top_expenses.length === 0 && (
                      <tr>
                        <td colSpan={3} className="text-center py-4 text-muted-foreground">No expenses this week.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      ) : null}
    </div>
  );
}
