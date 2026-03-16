import { api } from './client';

export type WeeklyDigest = {
  week: string;
  period: { start: string; end: string };
  summary: {
    total_income: number;
    total_expenses: number;
    net_flow: number;
    transaction_count: number;
  };
  week_over_week_change_pct: number;
  category_breakdown: Array<{ category: string; amount: number }>;
  top_expense: { amount: number; notes: string; date: string } | null;
  upcoming_bills: Array<{ name: string; amount: number; due_date: string }>;
  narrative: string;
};

export async function getWeeklyDigest(week?: string): Promise<WeeklyDigest> {
  const query = week ? `?week=${encodeURIComponent(week)}` : '';
  return api<WeeklyDigest>(`/digest/weekly${query}`);
}

export async function getDigestHistory(count = 4): Promise<WeeklyDigest[]> {
  return api<WeeklyDigest[]>(`/digest/weekly/history?count=${count}`);
}
