import { api } from './client';

export type WeeklyDigestSummary = {
  total_income: number;
  total_expenses: number;
  net_flow: number;
  transaction_count: number;
};

export type WeeklyDigestTrends = {
  previous_week: string;
  previous_income: number;
  previous_expenses: number;
  income_change_pct: number;
  expense_change_pct: number;
};

export type CategoryBreakdownItem = {
  category_id: number | null;
  category_name: string;
  amount: number;
  share_pct: number;
};

export type DailySpendingItem = {
  date: string;
  amount: number;
};

export type DigestTransaction = {
  id: number;
  description: string;
  amount: number;
  date: string;
  type: string;
  category_id: number | null;
  currency: string;
};

export type DigestBill = {
  id: number;
  name: string;
  amount: number;
  currency: string;
  next_due_date: string;
  cadence: string;
};

export type WeeklyDigest = {
  week: string;
  period: { start: string; end: string };
  summary: WeeklyDigestSummary;
  trends: WeeklyDigestTrends;
  category_breakdown: CategoryBreakdownItem[];
  daily_spending: DailySpendingItem[];
  transactions: DigestTransaction[];
  upcoming_bills: DigestBill[];
  insights: string[];
  method: 'gemini' | 'heuristic' | string;
  persona?: string;
  warnings?: string[];
};

function currentISOWeek(): string {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const startOfWeek1 = new Date(jan4.getTime() - (jan4.getDay() === 0 ? 6 : jan4.getDay() - 1) * 86400000);
  const diff = Math.floor((now.getTime() - startOfWeek1.getTime()) / (7 * 86400000));
  const week = diff + 1;
  return `${now.getFullYear()}-W${String(week).padStart(2, '0')}`;
}

export { currentISOWeek };

export async function getWeeklyDigest(params?: {
  week?: string;
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklyDigest> {
  const weekQuery = params?.week ? `?week=${encodeURIComponent(params.week)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<WeeklyDigest>(`/digest/weekly${weekQuery}`, { headers });
}
