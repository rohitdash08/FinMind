import { useMemo } from 'react';
import { format, subDays, eachDayOfInterval, isSameDay } from 'date-fns';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface HeatmapData {
  date: string;
  amount: number;
  count: number;
}

interface SpendingHeatmapProps {
  data: HeatmapData[];
  days?: number;
}

export function SpendingHeatmap({ data, days = 90 }: SpendingHeatmapProps) {
  const dateRange = useMemo(() => {
    const end = new Date();
    const start = subDays(end, days);
    return eachDayOfInterval({ start, end });
  }, [days]);

  const maxAmount = useMemo(() => {
    return Math.max(...data.map((d) => d.amount), 1);
  }, [data]);

  const getIntensity = (amount: number) => {
    if (amount === 0) return 0;
    const intensity = Math.ceil((amount / maxAmount) * 4);
    return Math.min(intensity, 4);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1">
        <TooltipProvider>
          {dateRange.map((day) => {
            const dayData = data.find((d) => isSameDay(new Date(d.date), day));
            const amount = dayData?.amount || 0;
            const intensity = getIntensity(amount);

            return (
              <Tooltip key={day.toISOString()}>
                <TooltipTrigger asChild>
                  <div
                    className={cn(
                      "h-3 w-3 rounded-sm transition-colors cursor-pointer",
                      intensity === 0 && "bg-muted hover:bg-muted/80",
                      intensity === 1 && "bg-primary/20 hover:bg-primary/30",
                      intensity === 2 && "bg-primary/40 hover:bg-primary/50",
                      intensity === 3 && "bg-primary/70 hover:bg-primary/80",
                      intensity === 4 && "bg-primary hover:bg-primary/90"
                    )}
                  />
                </TooltipTrigger>
                <TooltipContent>
                  <div className="text-xs">
                    <div className="font-semibold">{format(day, 'MMM d, yyyy')}</div>
                    <div className="text-muted-foreground">
                      {amount > 0 ? `$${amount.toFixed(2)} spent` : 'No expenses'}
                    </div>
                  </div>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </TooltipProvider>
      </div>
      <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
        <span>Less</span>
        <div className="flex gap-1">
          <div className="h-2 w-2 rounded-sm bg-muted" />
          <div className="h-2 w-2 rounded-sm bg-primary/20" />
          <div className="h-2 w-2 rounded-sm bg-primary/40" />
          <div className="h-2 w-2 rounded-sm bg-primary/70" />
          <div className="h-2 w-2 rounded-sm bg-primary" />
        </div>
        <span>More</span>
      </div>
    </div>
  );
}
