import { useMemo } from 'react';
import { type DashboardSummary } from '@/api/dashboard';
import { formatMoney } from '@/lib/currency';
import { TrendingDown, TrendingUp, ArrowUpRight, ArrowDownRight } from 'lucide-react';

type Props = { data: DashboardSummary | null; loading: boolean };

export function SpendingWidget({ data, loading }: Props) {
  const summary = useMemo(() => data?.summary ?? {
    monthly_income: 0, monthly_expenses: 0, net_flow: 0,
    upcoming_bills_total: 0, upcoming_bills_count: 0,
  }, [data]);

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="p-3 rounded-lg border bg-white">
        <div className="flex items-center gap-2 mb-1">
          <TrendingUp className="w-4 h-4 text-success" />
          <span className="text-xs text-muted-foreground">Income</span>
        </div>
        <div className="text-lg font-bold text-success">
          {loading ? '...' : formatMoney(summary.monthly_income)}
        </div>
      </div>
      <div className="p-3 rounded-lg border bg-white">
        <div className="flex items-center gap-2 mb-1">
          <TrendingDown className="w-4 h-4 text-destructive" />
          <span className="text-xs text-muted-foreground">Expenses</span>
        </div>
        <div className="text-lg font-bold">
          {loading ? '...' : formatMoney(summary.monthly_expenses)}
        </div>
      </div>
      <div className="col-span-2 p-3 rounded-lg border bg-white">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Net Flow</span>
          <span className={`text-lg font-bold ${summary.net_flow >= 0 ? 'text-success' : 'text-destructive'}`}>
            {loading ? '...' : formatMoney(summary.net_flow)}
          </span>
        </div>
        <div className="flex items-center mt-1">
          {summary.net_flow >= 0 ? (
            <ArrowUpRight className="w-3 h-3 text-success mr-1" />
          ) : (
            <ArrowDownRight className="w-3 h-3 text-destructive mr-1" />
          )}
          <span className="text-xs text-muted-foreground">
            {summary.net_flow >= 0 ? 'Surplus' : 'Deficit'}
          </span>
        </div>
      </div>
    </div>
  );
}
