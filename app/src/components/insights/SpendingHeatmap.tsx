import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSpendingHeatmap, HeatmapDataPoint } from '@/api/insights';
import { cn } from '@/lib/utils';
import { addMonths, format, isSameDay, subMonths, startOfMonth, endOfMonth, eachDayOfInterval } from 'date-fns';
import { CalendarDaysIcon, Loader2, MinusCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

interface SpendingHeatmapProps {
  // Optional: You could pass default date range or other props
}

type DateRange = {
  from: Date | undefined;
  to: Date | undefined;
};

// Helper to determine color intensity based on amount
const getColorIntensity = (amount: number, maxAmount: number): string => {
  if (amount === 0) return 'bg-gray-100 dark:bg-gray-800'; // No spending
  const intensity = Math.min(amount / maxAmount, 1); // Normalize to 0-1

  // Using a gradient from light red to dark red for increasing spending
  if (intensity > 0.8) return 'bg-red-700 text-white';
  if (intensity > 0.6) return 'bg-red-600 text-white';
  if (intensity > 0.4) return 'bg-red-500';
  if (intensity > 0.2) return 'bg-red-400';
  if (intensity > 0.05) return 'bg-red-300';
  return 'bg-red-200'; // Very low spending
};


export const SpendingHeatmap: React.FC<SpendingHeatmapProps> = () => {
  const defaultEndDate = new Date();
  // Show 3 months including current month, so start 2 months before current month's start
  const defaultStartDate = startOfMonth(subMonths(defaultEndDate, 2)); 

  const [dateRange, setDateRange] = useState<DateRange>({
    from: defaultStartDate,
    to: defaultEndDate,
  });

  // Format dates for API call
  const formattedStartDate = dateRange.from ? format(dateRange.from, 'yyyy-MM-dd') : '';
  const formattedEndDate = dateRange.to ? format(dateRange.to, 'yyyy-MM-dd') : '';

  const {
    data: heatmapData = [],
    isLoading,
    isError,
    error,
  } = useQuery<HeatmapDataPoint[], Error>(
    ['spendingHeatmap', formattedStartDate, formattedEndDate],
    () => getSpendingHeatmap({ startDate: formattedStartDate, endDate: formattedEndDate }),
    {
      enabled: !!dateRange.from && !!dateRange.to, // Only fetch if dates are selected
      keepPreviousData: true,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  );

  const dataMap = useMemo(() => {
    const map = new Map<string, number>();
    heatmapData.forEach((item) => {
      map.set(item.date, item.total_amount);
    });
    return map;
  }, [heatmapData]);

  const maxAmount = useMemo(() => {
    if (heatmapData.length === 0) return 1; // Avoid division by zero
    return Math.max(...heatmapData.map((item) => item.total_amount));
  }, [heatmapData]);

  const handleMonthNavigation = useCallback((direction: 'prev' | 'next') => {
    setDateRange((prev) => {
      const currentFrom = prev.from || defaultStartDate;
      const currentTo = prev.to || defaultEndDate;
      const offset = direction === 'prev' ? -1 : 1;

      // Navigate by full month chunks, starting from the 'from' date's month
      const newFrom = startOfMonth(addMonths(currentFrom, offset));
      const newTo = endOfMonth(addMonths(currentTo, offset));

      return { from: newFrom, to: newTo };
    });
  }, [defaultStartDate, defaultEndDate]);


  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Spending Trend Heatmap</CardTitle>
          <CardDescription>Visualize your spending intensity over time.</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-center p-6 min-h-[200px]">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="ml-2 text-muted-foreground">Loading spending data...</span>
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Spending Trend Heatmap</CardTitle>
          <CardDescription>Visualize your spending intensity over time.</CardDescription>
        </CardHeader>
        <CardContent className="p-6 text-red-500 flex items-center">
          <MinusCircle className="h-5 w-5 mr-2" />
          Error loading data: {error?.message || 'Unknown error'}
        </CardContent>
      </Card>
    );
  }

  // Group by week for display, ensuring full weeks are shown
  const weeks: Date[][] = [];
  let currentWeek: Date[] = [];
  const allDaysForDisplay = eachDayOfInterval({
    start: startOfMonth(dateRange.from || defaultStartDate),
    end: endOfMonth(dateRange.to || defaultEndDate),
  });

  allDaysForDisplay.forEach((day, index) => {
    // Fill in leading empty days if the first day of the range isn't Sunday (start of week)
    if (index === 0 && day.getDay() !== 0) {
      for (let i = 0; i < day.getDay(); i++) {
        currentWeek.push(new Date(0)); // Placeholder for empty day
      }
    }
    currentWeek.push(day);
    if (day.getDay() === 6 || index === allDaysForDisplay.length - 1) {
      // If Saturday or last day of the month/interval, fill trailing empty days
      while (currentWeek.length < 7) {
        currentWeek.push(new Date(0));
      }
      weeks.push(currentWeek);
      currentWeek = [];
    }
  });


  const weekDaysLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-2xl font-bold">Spending Trend Heatmap</CardTitle>
        <div className="flex space-x-2">
          <Button variant="outline" onClick={() => handleMonthNavigation('prev')}>Previous</Button>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                id="date"
                variant={"outline"}
                className={cn(
                  "w-[300px] justify-start text-left font-normal",
                  !dateRange.from && "text-muted-foreground"
                )}
              >
                <CalendarDaysIcon className="mr-2 h-4 w-4" />
                {dateRange.from ? (
                  dateRange.to ? (
                    <>
                      {format(dateRange.from, "MMM dd, yyy")} -{" "}
                      {format(dateRange.to, "MMM dd, yyy")}
                    </>
                  ) : (
                    format(dateRange.from, "MMM dd, yyy")
                  )
                ) : (
                  <span>Pick a date range</span>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end">
              <Calendar
                initialFocus
                mode="range"
                defaultMonth={dateRange.from}
                selected={dateRange}
                onSelect={setDateRange}
                numberOfMonths={2} // Show two months in the calendar picker
              />
            </PopoverContent>
          </Popover>
          <Button variant="outline" onClick={() => handleMonthNavigation('next')}>Next</Button>
        </div>
      </CardHeader>
      <CardContent>
        <CardDescription className="mb-4">Visualize your spending intensity over time. Deeper red indicates higher spending on that day.</CardDescription>
        <div className="grid grid-cols-7 gap-1 text-center text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
          {weekDaysLabels.map((day) => (
            <div key={day}>{day}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {weeks.map((week, weekIndex) => (
            <React.Fragment key={weekIndex}>
              {week.map((day, dayIndex) => {
                const dayStr = day.getTime() === 0 ? '' : format(day, 'yyyy-MM-dd');
                const amount = dayStr ? dataMap.get(dayStr) || 0 : 0;
                const tooltipText = dayStr ? `${format(day, 'MMM dd, yyyy')}: $${amount.toFixed(2)}` : '';

                return (
                  <div
                    key={`${weekIndex}-${dayIndex}`}
                    className={cn(
                      "relative h-8 w-8 flex items-center justify-center rounded-sm text-sm",
                      dayStr ? getColorIntensity(amount, maxAmount) : 'bg-transparent',
                      dayStr && isSameDay(day, new Date()) ? 'ring-2 ring-blue-500 dark:ring-blue-400' : ''
                    )}
                    title={tooltipText}
                  >
                    {dayStr ? format(day, 'd') : ''}
                    {amount > 0 && (
                        <span className="absolute -bottom-1 -right-1 text-[8px] px-1 rounded-sm opacity-90 bg-white dark:bg-gray-700 dark:text-gray-100 text-gray-800 border dark:border-gray-600">
                          {amount.toFixed(0)}
                        </span>
                      )}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};
