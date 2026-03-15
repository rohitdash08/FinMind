import { api } from './client';

export type WeeklyDigest = {
  week: string;
  period: {
    start: string;
    end: string;
  };
  total_spent: number;
  total_income: number;
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    share_pct: number;
  }>;
  week_over_week_change: number;
  trends: string[];
  insights: string[];
};

export async function getWeeklyDigest(week?: string): Promise<WeeklyDigest> {
  const query = week ? `?week=${encodeURIComponent(week)}` : '';
  return api<WeeklyDigest>(`/digest/weekly${query}`);
}
