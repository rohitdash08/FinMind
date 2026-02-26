import { useEffect, useMemo, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { getSpendingHeatmap, type HeatmapDay } from '@/api/insights';
import { useToast } from '@/hooks/use-toast';

const DAYS = ['Mon', '', 'Wed', '', 'Fri', '', ''];
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

function intensityClass(amount: number, max: number): string {
  if (amount === 0 || max === 0) return 'bg-muted';
  const ratio = amount / max;
  if (ratio < 0.25) return 'bg-green-200 dark:bg-green-900';
  if (ratio < 0.5) return 'bg-green-400 dark:bg-green-700';
  if (ratio < 0.75) return 'bg-green-500 dark:bg-green-500';
  return 'bg-green-700 dark:bg-green-300';
}

function buildGrid(year: number, data: HeatmapDay[]) {
  const map = new Map(data.map((d) => [d.date, d]));
  const jan1 = new Date(year, 0, 1);
  const startDow = (jan1.getDay() + 6) % 7; // Mon=0

  const cells: Array<{ date: string; total: number; count: number; blank?: boolean }> = [];
  // leading blanks
  for (let i = 0; i < startDow; i++) cells.push({ date: '', total: 0, count: 0, blank: true });

  const d = new Date(year, 0, 1);
  while (d.getFullYear() === year) {
    const iso = d.toISOString().slice(0, 10);
    const entry = map.get(iso);
    cells.push({ date: iso, total: entry?.total ?? 0, count: entry?.count ?? 0 });
    d.setDate(d.getDate() + 1);
  }

  // group into weeks (columns of 7)
  const weeks: typeof cells[] = [];
  for (let i = 0; i < cells.length; i += 7) {
    const week = cells.slice(i, i + 7);
    while (week.length < 7) week.push({ date: '', total: 0, count: 0, blank: true });
    weeks.push(week);
  }
  return weeks;
}

export function SpendingHeatmap() {
  const { toast } = useToast();
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [data, setData] = useState<HeatmapDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);

  useEffect(() => {
    setLoading(true);
    getSpendingHeatmap(year)
      .then(setData)
      .catch((e) => toast({ title: 'Heatmap error', description: String(e) }))
      .finally(() => setLoading(false));
  }, [year]);

  const weeks = useMemo(() => buildGrid(year, data), [year, data]);
  const maxTotal = useMemo(() => Math.max(...data.map((d) => d.total), 0), [data]);

  // figure out which week index each month starts
  const monthLabels = useMemo(() => {
    const labels: Array<{ month: string; col: number }> = [];
    let seen = -1;
    weeks.forEach((week, wi) => {
      for (const cell of week) {
        if (cell.blank || !cell.date) continue;
        const m = parseInt(cell.date.slice(5, 7), 10) - 1;
        if (m !== seen) {
          seen = m;
          labels.push({ month: MONTHS[m], col: wi });
        }
        break;
      }
    });
    return labels;
  }, [weeks]);

  return (
    <FinancialCard variant="financial">
      <FinancialCardHeader className="flex flex-row items-center justify-between">
        <FinancialCardTitle>Spending Heatmap</FinancialCardTitle>
        <div className="flex items-center gap-2">
          <button
            aria-label="Previous year"
            className="rounded px-2 py-1 text-sm border hover:bg-muted"
            onClick={() => setYear((y) => y - 1)}
          >
            ←
          </button>
          <span className="text-sm font-medium">{year}</span>
          <button
            aria-label="Next year"
            className="rounded px-2 py-1 text-sm border hover:bg-muted"
            onClick={() => setYear((y) => y + 1)}
          >
            →
          </button>
        </div>
      </FinancialCardHeader>
      <FinancialCardContent>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading heatmap…</div>
        ) : (
          <div className="relative overflow-x-auto">
            {/* Month labels */}
            <div className="flex ml-8 mb-1 text-xs text-muted-foreground">
              {monthLabels.map((ml) => (
                <span
                  key={ml.month}
                  className="absolute text-xs"
                  style={{ left: `${ml.col * 14 + 32}px` }}
                >
                  {ml.month}
                </span>
              ))}
            </div>
            <div className="flex gap-0 mt-5" role="grid" aria-label={`Spending heatmap for ${year}`}>
              {/* Day labels */}
              <div className="flex flex-col gap-[2px] mr-1 text-xs text-muted-foreground">
                {DAYS.map((d, i) => (
                  <div key={i} className="h-[12px] w-6 text-right leading-[12px]">{d}</div>
                ))}
              </div>
              {/* Grid */}
              {weeks.map((week, wi) => (
                <div key={wi} className="flex flex-col gap-[2px]">
                  {week.map((cell, di) => (
                    <div
                      key={di}
                      role="gridcell"
                      aria-label={cell.blank ? undefined : `${cell.date}: spent ${cell.total.toFixed(2)}`}
                      className={`h-[12px] w-[12px] rounded-sm ${
                        cell.blank ? 'bg-transparent' : intensityClass(cell.total, maxTotal)
                      } cursor-pointer transition-colors`}
                      onMouseEnter={(e) => {
                        if (cell.blank) return;
                        const rect = e.currentTarget.getBoundingClientRect();
                        setTooltip({
                          x: rect.left + rect.width / 2,
                          y: rect.top - 8,
                          text: `${cell.date}\n${cell.total.toFixed(2)} (${cell.count} txn${cell.count !== 1 ? 's' : ''})`,
                        });
                      }}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  ))}
                </div>
              ))}
            </div>
            {/* Legend */}
            <div className="flex items-center gap-1 mt-3 text-xs text-muted-foreground">
              <span>Less</span>
              <div className="h-[12px] w-[12px] rounded-sm bg-muted" />
              <div className="h-[12px] w-[12px] rounded-sm bg-green-200 dark:bg-green-900" />
              <div className="h-[12px] w-[12px] rounded-sm bg-green-400 dark:bg-green-700" />
              <div className="h-[12px] w-[12px] rounded-sm bg-green-500 dark:bg-green-500" />
              <div className="h-[12px] w-[12px] rounded-sm bg-green-700 dark:bg-green-300" />
              <span>More</span>
            </div>
            {/* Tooltip */}
            {tooltip && (
              <div
                className="fixed z-50 rounded bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md border whitespace-pre pointer-events-none"
                style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
              >
                {tooltip.text}
              </div>
            )}
          </div>
        )}
      </FinancialCardContent>
    </FinancialCard>
  );
}
