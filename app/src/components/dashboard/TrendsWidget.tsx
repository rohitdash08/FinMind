import { type DashboardSummary } from '@/api/dashboard';
import { formatMoney } from '@/lib/currency';
import { TrendingUp } from 'lucide-react';

type Props = { data: DashboardSummary | null; loading: boolean };

export function TrendsWidget({ data, loading }: Props) {
  const breakdown = data?.category_breakdown ?? [];
  const currentMonthExpenses = data?.summary?.monthly_expenses ?? 0;

  if (loading) return <div className="text-sm text-muted-foreground">Loading...</div>;

  if (breakdown.length === 0) {
    return <div className="text-sm text-muted-foreground">No data to show trends.</div>;
  }

  return (
    <div className="space-y-3">
      {breakdown.slice(0, 5).map((row) => {
        const pct = currentMonthExpenses > 0
          ? (row.amount / currentMonthExpenses) * 100
          : 0;
        return (
          <div key={`${row.category_id ?? 'x'}-${row.category_name}`} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span>{row.category_name}</span>
              <span className="text-muted-foreground text-xs">
                {formatMoney(row.amount)} ({pct.toFixed(0)}%)
              </span>
            </div>
            <div className="chart-track">
              <div
                className="chart-fill-primary"
                style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
