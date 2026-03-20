import { useEffect, useMemo, useState } from 'react';
import { getSpendingHeatmap, type HeatmapEntry } from '@/api/expenses';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';

const DAYS_OF_WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const WEEKS = 52;
const TOTAL_DAYS = WEEKS * 7;

function getColor(amount: number, max: number): string {
  if (amount === 0) return 'bg-muted';
  const ratio = max > 0 ? amount / max : 0;
  if (ratio < 0.25) return 'bg-green-300 dark:bg-green-700';
  if (ratio < 0.5) return 'bg-yellow-300 dark:bg-yellow-500';
  if (ratio < 0.75) return 'bg-orange-400 dark:bg-orange-500';
  return 'bg-red-500 dark:bg-red-600';
}

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function SpendingHeatmap() {
  const [data, setData] = useState<HeatmapEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredCell, setHoveredCell] = useState<{ date: string; amount: number; x: number; y: number } | null>(null);

  useEffect(() => {
    setLoading(true);
    getSpendingHeatmap(12)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load heatmap'))
      .finally(() => setLoading(false));
  }, []);

  const { grid, maxAmount } = useMemo(() => {
    const lookup = new Map<string, number>();
    for (const entry of data) {
      lookup.set(entry.date, (lookup.get(entry.date) ?? 0) + entry.amount);
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Build grid: TOTAL_DAYS ending on today
    const cells: { date: string; amount: number; dayOfWeek: number }[] = [];
    let max = 0;
    for (let i = TOTAL_DAYS - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = formatDate(d);
      const amount = lookup.get(key) ?? 0;
      if (amount > max) max = amount;
      cells.push({ date: key, amount, dayOfWeek: (d.getDay() + 6) % 7 }); // Monday=0
    }

    return { grid: cells, maxAmount: max };
  }, [data]);

  // Organize into columns (weeks)
  const weeks = useMemo(() => {
    const result: typeof grid[] = [];
    for (let w = 0; w < WEEKS; w++) {
      result.push(grid.slice(w * 7, w * 7 + 7));
    }
    return result;
  }, [grid]);

  if (loading) {
    return (
      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <FinancialCardTitle>Spending Heatmap</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>Loading heatmap...</FinancialCardContent>
      </FinancialCard>
    );
  }

  if (error) {
    return (
      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <FinancialCardTitle>Spending Heatmap</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="text-red-600">{error}</div>
        </FinancialCardContent>
      </FinancialCard>
    );
  }

  return (
    <FinancialCard variant="financial">
      <FinancialCardHeader>
        <FinancialCardTitle>Spending Heatmap</FinancialCardTitle>
      </FinancialCardHeader>
      <FinancialCardContent>
        <div className="relative overflow-x-auto">
          <div className="flex gap-[3px]" data-testid="heatmap-grid">
            {/* Day-of-week labels */}
            <div className="flex flex-col gap-[3px] pr-1">
              {DAYS_OF_WEEK.map((d) => (
                <div key={d} className="h-[13px] text-[10px] leading-[13px] text-muted-foreground">
                  {d}
                </div>
              ))}
            </div>
            {/* Week columns */}
            {weeks.map((week, wi) => (
              <div key={wi} className="flex flex-col gap-[3px]">
                {week.map((cell) => (
                  <div
                    key={cell.date}
                    data-testid="heatmap-cell"
                    className={`h-[13px] w-[13px] rounded-sm ${getColor(cell.amount, maxAmount)} cursor-pointer transition-transform hover:scale-125`}
                    onMouseEnter={(e) => {
                      const rect = (e.target as HTMLElement).getBoundingClientRect();
                      setHoveredCell({ date: cell.date, amount: cell.amount, x: rect.left, y: rect.top });
                    }}
                    onMouseLeave={() => setHoveredCell(null)}
                  />
                ))}
              </div>
            ))}
          </div>

          {/* Tooltip */}
          {hoveredCell && (
            <div
              data-testid="heatmap-tooltip"
              className="pointer-events-none fixed z-50 rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md"
              style={{ left: hoveredCell.x, top: hoveredCell.y - 36 }}
            >
              {hoveredCell.date}: {hoveredCell.amount > 0 ? `$${hoveredCell.amount.toFixed(2)}` : 'No spending'}
            </div>
          )}

          {/* Legend */}
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <span>Less</span>
            <div className="h-[11px] w-[11px] rounded-sm bg-muted" />
            <div className="h-[11px] w-[11px] rounded-sm bg-green-300 dark:bg-green-700" />
            <div className="h-[11px] w-[11px] rounded-sm bg-yellow-300 dark:bg-yellow-500" />
            <div className="h-[11px] w-[11px] rounded-sm bg-orange-400 dark:bg-orange-500" />
            <div className="h-[11px] w-[11px] rounded-sm bg-red-500 dark:bg-red-600" />
            <span>More</span>
          </div>
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}
