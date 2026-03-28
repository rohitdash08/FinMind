import { apiClient } from './client';

export interface WeeklyCategoryBreakdown {
  category: string;
  amount: number;
  percentage: number;
  change: number; // percentage change from previous week
  transactionCount: number;
}

export interface WeeklyTrend {
  week: string; // ISO date of week start
  income: number;
  expenses: number;
  savings: number;
  savingsRate: number;
}

export interface WeeklyInsight {
  type: 'warning' | 'success' | 'info' | 'tip';
  title: string;
  description: string;
  metric?: string;
  change?: number;
}

export interface WeeklySummary {
  weekStart: string;
  weekEnd: string;
  totalIncome: number;
  totalExpenses: number;
  netSavings: number;
  savingsRate: number;
  topCategories: WeeklyCategoryBreakdown[];
  budgetAdherence: number; // percentage of budget used
  budgetStatus: 'under' | 'on-track' | 'over';
  insights: WeeklyInsight[];
  trends: WeeklyTrend[];
  transactionCount: number;
}

export interface WeeklySummaryResponse {
  current: WeeklySummary;
  previous: WeeklySummary | null;
}

export const getWeeklySummary = async (weekStart?: string): Promise<WeeklySummaryResponse> => {
  const params = weekStart ? { weekStart } : {};
  const response = await apiClient.get('/weekly-summary', { params });
  return response.data;
};

export const getWeeklyTrends = async (weeks: number = 12): Promise<WeeklyTrend[]> => {
  const response = await apiClient.get('/weekly-summary/trends', { params: { weeks } });
  return response.data;
};

export const getWeeklyCategoryBreakdown = async (weekStart?: string): Promise<WeeklyCategoryBreakdown[]> => {
  const params = weekStart ? { weekStart } : {};
  const response = await apiClient.get('/weekly-summary/categories', { params });
  return response.data;
};
