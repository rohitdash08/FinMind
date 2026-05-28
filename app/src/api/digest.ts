/**
 * Smart Digest API — weekly financial summary with AI insights.
 */

import { api } from './client';

// ── Types ────────────────────────────────────────────────────────────

export type DigestPeriod = {
  start: string;       // YYYY-MM-DD
  end: string;         // YYYY-MM-DD
  label: string;       // Human-readable week label
};

export type DigestSummary = {
  income: number;
  expenses: number;
  net_flow: number;
};

export type DigestCategory = {
  category_id: number | null;
  category_name: string;
  amount: number;
  share_pct: number;
};

export type DigestDailySpending = {
  date: string;        // YYYY-MM-DD
  amount: number;
};

export type DigestUpcomingBill = {
  id: number;
  name: string;
  amount: number;
  currency: string;
  due_date: string;
  days_until_due: number;
};

export type DigestTopTransaction = {
  id: number;
  description: string;
  amount: number;
  date: string;
  category_id: number | null;
};

export type DigestTrends = {
  week_over_week_change_pct: number;
  spending_direction: 'up' | 'down' | 'stable';
  top_category: DigestCategory | null;
  alerts: string[];
};

export type DigestAIInsights = {
  summary: string;
  highlights: string[];
  tips: string[];
  mood: 'great' | 'good' | 'okay' | 'needs_attention';
};

export type WeeklyDigest = {
  period: DigestPeriod;
  summary: DigestSummary;
  comparison: {
    previous_week: DigestSummary;
    trends: DigestTrends;
  };
  categories: DigestCategory[];
  daily_spending: DigestDailySpending[];
  upcoming_bills: DigestUpcomingBill[];
  top_transactions: DigestTopTransaction[];
  ai_insights: DigestAIInsights | null;
  method: 'gemini' | 'heuristic';
};

// ── API Call ─────────────────────────────────────────────────────────

export async function getWeeklyDigest(params?: {
  date?: string;
  geminiApiKey?: string;
}): Promise<WeeklyDigest> {
  const dateQuery = params?.date ? `?date=${encodeURIComponent(params.date)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  return api<WeeklyDigest>(`/digest/weekly${dateQuery}`, { headers });
}
