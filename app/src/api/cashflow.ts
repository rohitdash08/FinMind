import {
  addDays,
  addMonths,
  addWeeks,
  addYears,
  format,
  isAfter,
  isBefore,
  parseISO,
  startOfDay,
  endOfDay
} from 'date-fns';
import type { RecurringExpense } from './expenses';
import type { Bill } from './bills';

export type ForecastItem = {
  id: string;
  name: string;
  amount: number;
  currency: string;
  type: 'recurring' | 'bill';
  isIncome: boolean;
};

export type ForecastPoint = {
  date: string;
  outflow: number;
  inflow: number;
  netFlow: number;
  cumulativeNet: number;
  items: ForecastItem[];
};

export function generateForecast(
  recurringExpenses: RecurringExpense[],
  bills: Bill[],
  horizonDays: 30 | 60 | 90,
  fromDate: Date = new Date()
): ForecastPoint[] {
  const start = startOfDay(fromDate);
  const end = addDays(start, horizonDays - 1);
  const endOfEnd = endOfDay(end);

  const pointsMap: Record<string, ForecastPoint> = {};
  for (let i = 0; i < horizonDays; i++) {
    const current = addDays(start, i);
    const dateStr = format(current, 'yyyy-MM-dd');
    pointsMap[dateStr] = {
      date: dateStr,
      outflow: 0,
      inflow: 0,
      netFlow: 0,
      cumulativeNet: 0,
      items: [],
    };
  }

  const addItemToDay = (date: Date, item: ForecastItem) => {
    const dateStr = format(date, 'yyyy-MM-dd');
    if (pointsMap[dateStr]) {
      pointsMap[dateStr].items.push(item);
      if (item.isIncome) {
        pointsMap[dateStr].inflow += item.amount;
      } else {
        pointsMap[dateStr].outflow += item.amount;
      }
      pointsMap[dateStr].netFlow = pointsMap[dateStr].inflow - pointsMap[dateStr].outflow;
    }
  };

  recurringExpenses.forEach((expense) => {
    if (!expense.active) return;
    const startDate = startOfDay(parseISO(expense.start_date));
    const endDate = expense.end_date ? endOfDay(parseISO(expense.end_date)) : null;
    const isIncome = expense.expense_type === 'INCOME';

    const fItem: ForecastItem = {
      id: `recurring-${expense.id}`,
      name: expense.description || 'Recurring Expense',
      amount: Number(expense.amount),
      currency: expense.currency,
      type: 'recurring',
      isIncome,
    };

    let current = startDate;
    let i = 0;

    while (isBefore(current, endOfEnd) || format(current, 'yyyy-MM-dd') === format(endOfEnd, 'yyyy-MM-dd')) {
      if (endDate && isAfter(current, endDate) && format(current, 'yyyy-MM-dd') !== format(endDate, 'yyyy-MM-dd')) {
        break;
      }
      
      if (!isBefore(current, start)) {
        addItemToDay(current, fItem);
      }

      if (expense.cadence === 'DAILY') {
        current = addDays(current, 1);
      } else if (expense.cadence === 'WEEKLY') {
        current = addWeeks(current, 1);
      } else if (expense.cadence === 'MONTHLY') {
        i++;
        current = addMonths(startDate, i);
      } else if (expense.cadence === 'YEARLY') {
        i++;
        current = addYears(startDate, i);
      } else {
        break;
      }
    }
  });

  bills.forEach((bill) => {
    if (bill.paid_at) return;
    if (!bill.next_due_date) return;

    const dueDateRaw = startOfDay(parseISO(bill.next_due_date));
    const fItem: ForecastItem = {
      id: `bill-${bill.id}`,
      name: bill.name,
      amount: Number(bill.amount),
      currency: bill.currency || 'USD',
      type: 'bill',
      isIncome: false,
    };

    const cadence = bill.cadence || 'ONCE';

    if (cadence === 'ONCE') {
      // Past-due unpaid one-time bill: show it on the first day of the forecast
      const effectiveDate = isBefore(dueDateRaw, start) ? start : dueDateRaw;
      if (!isAfter(effectiveDate, endOfEnd)) {
        addItemToDay(effectiveDate, fItem);
      }
    } else {
      // For recurring bills, advance from next_due_date to first occurrence >= start
      let i = 0;
      let current = dueDateRaw;

      // Fast-forward past-due recurring bills to first occurrence within forecast window
      while (isBefore(current, start)) {
        i++;
        if (cadence === 'WEEKLY') {
          current = addWeeks(dueDateRaw, i);
        } else if (cadence === 'MONTHLY') {
          current = addMonths(dueDateRaw, i);
        } else if (cadence === 'YEARLY') {
          current = addYears(dueDateRaw, i);
        } else {
          break;
        }
      }

      while (!isAfter(current, endOfEnd)) {
        addItemToDay(current, fItem);

        i++;
        if (cadence === 'WEEKLY') {
          current = addWeeks(dueDateRaw, i);
        } else if (cadence === 'MONTHLY') {
          current = addMonths(dueDateRaw, i);
        } else if (cadence === 'YEARLY') {
          current = addYears(dueDateRaw, i);
        } else {
          break;
        }
      }
    }
  });

  const points: ForecastPoint[] = [];
  let cumulative = 0;
  
  for (let i = 0; i < horizonDays; i++) {
    const current = addDays(start, i);
    const dateStr = format(current, 'yyyy-MM-dd');
    const pt = pointsMap[dateStr];
    cumulative += pt.netFlow;
    pt.cumulativeNet = cumulative;
    points.push(pt);
  }

  return points;
}

export function aggregateByWeek(points: ForecastPoint[]): ForecastPoint[] {
  const result: ForecastPoint[] = [];
  let currentWeek: ForecastPoint | null = null;
  
  points.forEach((point, index) => {
    if (index % 7 === 0) {
      if (currentWeek) {
        result.push(currentWeek);
      }
      currentWeek = {
        date: point.date,
        outflow: point.outflow,
        inflow: point.inflow,
        netFlow: point.netFlow,
        cumulativeNet: point.cumulativeNet,
        items: [...point.items],
      };
    } else if (currentWeek) {
      currentWeek.outflow += point.outflow;
      currentWeek.inflow += point.inflow;
      currentWeek.netFlow += point.netFlow;
      currentWeek.cumulativeNet = point.cumulativeNet;
      currentWeek.items.push(...point.items);
    }
  });

  if (currentWeek) {
    result.push(currentWeek);
  }

  return result;
}

export function computeSummary(points: ForecastPoint[]) {
  if (points.length === 0) {
    return { totalOutflow: 0, totalInflow: 0, netFlow: 0, worstDay: null, bestDay: null };
  }

  let totalOutflow = 0;
  let totalInflow = 0;
  let netFlow = 0;
  let worstDay = points[0];
  let bestDay = points[0];

  points.forEach((p) => {
    totalOutflow += p.outflow;
    totalInflow += p.inflow;
    netFlow += p.netFlow;
    if (p.netFlow < worstDay.netFlow) worstDay = p;
    if (p.netFlow > bestDay.netFlow) bestDay = p;
  });

  return { totalOutflow, totalInflow, netFlow, worstDay, bestDay };
}
