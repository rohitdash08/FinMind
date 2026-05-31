import { useMemo } from 'react';
import { type DashboardSummary } from '@/api/dashboard';
import { formatMoney } from '@/lib/currency';
import { PiggyBank, Target } from 'lucide-react';

type Props = { data: DashboardSummary | null; loading: boolean };

export function SavingsWidget({ data, loading }: Props) {
  const summary = data?.summary;
  const income = summary?.monthly_income ?? 0;
  const expenses = summary?.monthly_expenses ?? 0;
  const net = income - expenses;
  const savingsRate = income > 0 ? (net / income) * 100 : 0;
  const target = 20;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <PiggyBank className="w-5 h-5 text-primary" />
          <span className="text-sm text-muted-foreground">Saved this month</span>
        </div>
        <span className="text-lg font-bold text-success">
          {loading ? '...' : formatMoney(Math.max(0, net))}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-accent" />
          <span className="text-xs text-muted-foreground">Savings Rate</span>
        </div>
        <span className="text-sm font-semibold">
          {loading ? '...' : `${savingsRate.toFixed(1)}%`}
        </span>
      </div>
      <div className="chart-track">
        <div
          className={`chart-fill h-3 ${savingsRate >= target ? 'chart-fill-success' : 'chart-fill-warning'}`}
          style={{ width: `${Math.min(100, savingsRate * 2)}%` }}
        />
      </div>
      <div className="text-xs text-muted-foreground">
        Target: {target}% savings rate
        {savingsRate < target && ` (${(target - savingsRate).toFixed(1)}% to go)`}
      </div>
    </div>
  );
}
