import { api } from './client';
import { subWeeks, startOfWeek, endOfWeek, format, subDays } from 'date-fns';

export type WeeklyInsight = {
  type: 'trend' | 'alert' | 'tip' | 'achievement';
  title: string;
  description: string;
  severity?: 'positive' | 'negative' | 'neutral';
};

export type WeeklySummary = {
  week_start: string;
  week_end: string;
  total_income: number;
  total_expenses: number;
  net_flow: number;
  transaction_count: number;
  top_expense_category: {
    name: string;
    amount: number;
    percentage: number;
  } | null;
  comparison_to_last_week: {
    expense_change_pct: number;
    income_change_pct: number;
  };
  insights: WeeklyInsight[];
  daily_breakdown: Array<{
    date: string;
    income: number;
    expenses: number;
  }>;
};

// Mock implementation for development until backend endpoint is ready
function generateMockWeeklySummary(weekOffset: number): WeeklySummary {
  const now = new Date();
  const targetWeek = subWeeks(now, -weekOffset);
  const weekStart = startOfWeek(targetWeek, { weekStartsOn: 1 });
  const weekEnd = endOfWeek(targetWeek, { weekStartsOn: 1 });
  
  // Generate realistic mock data
  const totalIncome = Math.round(Math.random() * 2000 + 3000);
  const totalExpenses = Math.round(Math.random() * 1500 + 1000);
  const netFlow = totalIncome - totalExpenses;
  const transactionCount = Math.round(Math.random() * 20 + 5);
  
  // Generate daily breakdown
  const dailyBreakdown = [];
  for (let i = 0; i < 7; i++) {
    const date = subDays(weekEnd, 6 - i);
    dailyBreakdown.push({
      date: format(date, 'yyyy-MM-dd'),
      income: i === 4 ? totalIncome * 0.8 : Math.round(Math.random() * 100),
      expenses: Math.round(Math.random() * (totalExpenses / 7) * 2),
    });
  }
  
  // Generate insights based on the data
  const insights: WeeklyInsight[] = [];
  
  if (netFlow > 1000) {
    insights.push({
      type: 'achievement',
      title: 'Great Savings Week!',
      description: `You saved ${(netFlow / totalIncome * 100).toFixed(1)}% of your income this week.`,
      severity: 'positive',
    });
  }
  
  if (totalExpenses > totalIncome * 0.8) {
    insights.push({
      type: 'alert',
      title: 'High Spending Alert',
      description: 'Your expenses are approaching your income. Consider reviewing discretionary spending.',
      severity: 'negative',
    });
  }
  
  insights.push({
    type: 'tip',
    title: 'Budgeting Tip',
    description: 'Try the 50/30/20 rule: 50% needs, 30% wants, 20% savings.',
    severity: 'neutral',
  });
  
  if (Math.random() > 0.5) {
    insights.push({
      type: 'trend',
      title: 'Spending Pattern',
      description: 'Weekend expenses are typically higher. Plan ahead to stay on budget.',
      severity: 'neutral',
    });
  }
  
  return {
    week_start: format(weekStart, 'yyyy-MM-dd'),
    week_end: format(weekEnd, 'yyyy-MM-dd'),
    total_income: totalIncome,
    total_expenses: totalExpenses,
    net_flow: netFlow,
    transaction_count: transactionCount,
    top_expense_category: {
      name: ['Food & Dining', 'Transportation', 'Shopping', 'Entertainment'][Math.floor(Math.random() * 4)],
      amount: Math.round(totalExpenses * 0.35),
      percentage: 35,
    },
    comparison_to_last_week: {
      expense_change_pct: (Math.random() - 0.5) * 20,
      income_change_pct: (Math.random() - 0.5) * 10,
    },
    insights,
    daily_breakdown: dailyBreakdown,
  };
}

export async function getWeeklySummary(weekOffset: number = 0): Promise<WeeklySummary> {
  // Try to call the real API first, fallback to mock if not available
  try {
    return await api<WeeklySummary>(`/insights/weekly-summary?week_offset=${weekOffset}`);
  } catch {
    // Return mock data for development/testing
    return generateMockWeeklySummary(weekOffset);
  }
}
