import { generateForecast, aggregateByWeek, computeSummary } from '../api/cashflow';
import type { RecurringExpense } from '../api/expenses';
import type { Bill } from '../api/bills';

describe('cashflow engine', () => {
  const baseDate = new Date('2024-01-01T12:00:00Z');

  it('1. returns array of horizonDays length with 0 values for empty inputs', () => {
    const points = generateForecast([], [], 30, baseDate);
    expect(points).toHaveLength(30);
    expect(points[0].outflow).toBe(0);
    expect(points[0].inflow).toBe(0);
    expect(points[29].netFlow).toBe(0);
  });

  it('2. daily recurring expense appears every day', () => {
    const expense: RecurringExpense = {
      id: 1,
      amount: 10,
      currency: 'USD',
      expense_type: 'UTILITIES',
      category_id: null,
      description: 'Daily Coffee',
      cadence: 'DAILY',
      start_date: '2024-01-01',
      end_date: null,
      active: true,
    };
    const points = generateForecast([expense], [], 30, baseDate);
    expect(points[0].outflow).toBe(10);
    expect(points[29].outflow).toBe(10);
    expect(points[0].items[0].name).toBe('Daily Coffee');
  });

  it('3. monthly recurring on 15th only appears on 15th of each month', () => {
    const expense: RecurringExpense = {
      id: 2,
      amount: 50,
      currency: 'USD',
      expense_type: 'SUBSCRIPTION',
      category_id: null,
      description: 'Monthly Sub',
      cadence: 'MONTHLY',
      start_date: '2024-01-15',
      end_date: null,
      active: true,
    };
    const points = generateForecast([expense], [], 60, baseDate);
    
    expect(points[14].outflow).toBe(50);
    expect(points[14].date).toBe('2024-01-15');
    
    expect(points[45].outflow).toBe(50);
    expect(points[45].date).toBe('2024-02-15');

    expect(points[0].outflow).toBe(0);
  });

  it('4. weekly recurring appears every 7 days', () => {
    const expense: RecurringExpense = {
      id: 3,
      amount: 20,
      currency: 'USD',
      expense_type: 'GROCERIES',
      category_id: null,
      description: 'Weekly Groceries',
      cadence: 'WEEKLY',
      start_date: '2024-01-01',
      end_date: null,
      active: true,
    };
    const points = generateForecast([expense], [], 30, baseDate);
    expect(points[0].outflow).toBe(20);
    expect(points[7].outflow).toBe(20);
    expect(points[14].outflow).toBe(20);
    expect(points[1].outflow).toBe(0);
  });

  it('5. inactive recurring never appears', () => {
    const expense: RecurringExpense = {
      id: 4,
      amount: 100,
      currency: 'USD',
      expense_type: 'OTHER',
      category_id: null,
      description: 'Inactive',
      cadence: 'DAILY',
      start_date: '2024-01-01',
      end_date: null,
      active: false,
    };
    const points = generateForecast([expense], [], 30, baseDate);
    expect(points[0].outflow).toBe(0);
    expect(points[0].items).toHaveLength(0);
  });

  it('6. recurring after end_date is excluded', () => {
    const expense: RecurringExpense = {
      id: 5,
      amount: 30,
      currency: 'USD',
      expense_type: 'OTHER',
      category_id: null,
      description: 'Ends Soon',
      cadence: 'DAILY',
      start_date: '2024-01-01',
      end_date: '2024-01-05',
      active: true,
    };
    const points = generateForecast([expense], [], 30, baseDate);
    expect(points[0].outflow).toBe(30);
    expect(points[4].outflow).toBe(30);
    expect(points[5].outflow).toBe(0);
  });

  it('7. bill with ONCE cadence appears exactly once', () => {
    const bill: Bill = {
      id: 1,
      name: 'One-time Bill',
      amount: 100,
      next_due_date: '2024-01-10',
      cadence: 'ONCE',
    };
    const points = generateForecast([], [bill], 30, baseDate);
    expect(points[9].outflow).toBe(100);
    expect(points[9].date).toBe('2024-01-10');
    expect(points[10].outflow).toBe(0);
  });

  it('8. bill with MONTHLY cadence appears monthly', () => {
    const bill: Bill = {
      id: 2,
      name: 'Monthly Bill',
      amount: 200,
      next_due_date: '2024-01-05',
      cadence: 'MONTHLY',
    };
    const points = generateForecast([], [bill], 60, baseDate);
    expect(points[4].outflow).toBe(200);
    expect(points[35].outflow).toBe(200);
  });

  it('9. bill already paid is excluded', () => {
    const bill: Bill = {
      id: 3,
      name: 'Paid Bill',
      amount: 100,
      next_due_date: '2024-01-02',
      cadence: 'ONCE',
      paid_at: '2024-01-01T10:00:00Z',
    };
    const points = generateForecast([], [bill], 30, baseDate);
    expect(points[1].outflow).toBe(0);
  });

  it('10. income recurring is treated as inflow', () => {
    const expense: RecurringExpense = {
      id: 6,
      amount: 1000,
      currency: 'USD',
      expense_type: 'INCOME',
      category_id: null,
      description: 'Salary',
      cadence: 'MONTHLY',
      start_date: '2024-01-01',
      end_date: null,
      active: true,
    };
    const points = generateForecast([expense], [], 30, baseDate);
    expect(points[0].inflow).toBe(1000);
    expect(points[0].outflow).toBe(0);
    expect(points[0].netFlow).toBe(1000);
    expect(points[0].cumulativeNet).toBe(1000);
  });

  it('11. computeSummary correctly computes totals', () => {
    const expense: RecurringExpense = {
      id: 7,
      amount: 1000,
      currency: 'USD',
      expense_type: 'INCOME',
      category_id: null,
      description: 'Salary',
      cadence: 'MONTHLY',
      start_date: '2024-01-01',
      end_date: null,
      active: true,
    };
    const bill: Bill = {
      id: 4,
      name: 'Rent',
      amount: 800,
      next_due_date: '2024-01-05',
      cadence: 'ONCE',
    };
    const points = generateForecast([expense], [bill], 30, baseDate);
    const summary = computeSummary(points);
    
    expect(summary.totalInflow).toBe(1000);
    expect(summary.totalOutflow).toBe(800);
    expect(summary.netFlow).toBe(200);
    expect(summary.bestDay?.netFlow).toBe(1000);
    expect(summary.worstDay?.netFlow).toBe(-800);
  });

  it('13. past-due ONCE bill (unpaid) is mapped to first day of forecast', () => {
    const bill: Bill = {
      id: 10,
      name: 'Overdue Bill',
      amount: 150,
      next_due_date: '2023-12-01',
      cadence: 'ONCE',
    };
    const points = generateForecast([], [bill], 30, baseDate);
    expect(points[0].outflow).toBe(150);
    expect(points[0].date).toBe('2024-01-01');
  });

  it('14. past-due recurring bill fast-forwards to first occurrence within forecast', () => {
    const bill: Bill = {
      id: 11,
      name: 'Overdue Monthly',
      amount: 300,
      next_due_date: '2023-11-10',
      cadence: 'MONTHLY',
    };
    const points = generateForecast([], [bill], 30, baseDate);
    const jan10 = points.find((p) => p.date === '2024-01-10');
    expect(jan10).toBeDefined();
    expect(jan10!.outflow).toBe(300);
    expect(points[0].outflow).toBe(0);
  });

  it('15. MONTHLY cadence respects calendar months not 30-day multiples', () => {
    const expense: RecurringExpense = {
      id: 8,
      amount: 100,
      currency: 'USD',
      expense_type: 'SUBSCRIPTION',
      category_id: null,
      description: 'End of Month',
      cadence: 'MONTHLY',
      start_date: '2024-01-31',
      end_date: null,
      active: true,
    };
    const points = generateForecast([expense], [], 60, baseDate);
    const jan31 = points.find((p) => p.date === '2024-01-31');
    const feb29 = points.find((p) => p.date === '2024-02-29');
    expect(jan31).toBeDefined();
    expect(jan31!.outflow).toBe(100);
    expect(feb29).toBeDefined();
    expect(feb29!.outflow).toBe(100);
  });

  it('16. YEARLY cadence appears once per year', () => {
    const expense: RecurringExpense = {
      id: 9,
      amount: 500,
      currency: 'USD',
      expense_type: 'INSURANCE',
      category_id: null,
      description: 'Annual Insurance',
      cadence: 'YEARLY',
      start_date: '2024-01-15',
      end_date: null,
      active: true,
    };
    const points = generateForecast([expense], [], 30, baseDate);
    const jan15 = points.find((p) => p.date === '2024-01-15');
    expect(jan15).toBeDefined();
    expect(jan15!.outflow).toBe(500);
    const nonJan15 = points.filter((p) => p.date !== '2024-01-15');
    nonJan15.forEach((p) => expect(p.outflow).toBe(0));
  });

  it('17. recurring with start_date in the future only appears from that date', () => {
    const expense: RecurringExpense = {
      id: 10,
      amount: 50,
      currency: 'USD',
      expense_type: 'OTHER',
      category_id: null,
      description: 'Future Sub',
      cadence: 'DAILY',
      start_date: '2024-01-15',
      end_date: null,
      active: true,
    };
    const points = generateForecast([expense], [], 30, baseDate);
    expect(points[0].outflow).toBe(0);
    expect(points[13].outflow).toBe(0);
    const jan15 = points.find((p) => p.date === '2024-01-15');
    expect(jan15!.outflow).toBe(50);
  });

  it('18. aggregateByWeek returns correct number of weekly buckets', () => {
    const points = generateForecast([], [], 30, baseDate);
    const weeks = aggregateByWeek(points);
    expect(weeks).toHaveLength(5);
    expect(weeks[0].date).toBe('2024-01-01');
    expect(weeks[1].date).toBe('2024-01-08');
  });
});
