import { useMemo } from 'react';
import { type DashboardSummary } from '@/api/dashboard';
import { formatMoney } from '@/lib/currency';
import { DollarSign } from 'lucide-react';

type Props = { data: DashboardSummary | null; loading: boolean };

export function BudgetWidget({ data, loading }: Props) {
  const summary = data?.summary;
  const budget = 2000;
  const spent = summary?.monthly_expenses ?? 0;
  const pct = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">Budget Used</span>
        <span className="text-sm font-semibold">
          {loading ? '...' : `${pct.toFixed(0)}%`}
        </span>
      </div>
      <div className="chart-track">
        <div
          className={`chart-fill h-3 ${
            pct > 90 ? 'chart-fill-danger' : pct > 70 ? 'chart-fill-warning' : 'chart-fill-success'
          }`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Spent: {loading ? '...' : formatMoney(spent)}</span>
        <span>Budget: {formatMoney(budget)}</span>
      </div>
      {pct > 90 && (
        <div className="flex items-center gap-1 text-xs text-destructive">
          <DollarSign className="w-3 h-3" />
          Over budget!
        </div>
      )}
    </div>
  );
}
