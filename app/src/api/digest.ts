import { api } from './client';

export interface WeekOverWeekEntry {
  current: number;
  previous: number;
  change: number;
  change_pct: number;
}

export interface WeeklyDigest {
  week: string;
  period: { start: string; end: string };
  total_spent: number;
  category_breakdown: Record<string, number>;
  week_over_week_change: Record<string, WeekOverWeekEntry>;
  trends: string[];
  insights: string[];
}

export async function fetchWeeklyDigest(week?: string): Promise<WeeklyDigest> {
  const params = week ? `?week=${week}` : '';
  return api<WeeklyDigest>(`/digest/weekly${params}`);
}
