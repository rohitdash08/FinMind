/**
 * 每周财务摘要 API
 */
import { apiClient } from './client';

export interface WeeklyDigestSummary {
  week_start: string;
  week_end: string;
  method: 'gemini' | 'heuristic';
  subject: string;
  greeting: string;
  highlights: string[];
  insights: string[];
  warnings: string[];
  tips: string[];
  closing: string;
  week_data: WeekData;
  previous_week_data: WeekData;
  comparison: WeekComparison;
  persona: string;
}

export interface WeekData {
  week_start: string;
  week_end: string;
  total_income: number;
  total_expenses: number;
  net_flow: number;
  categories: Record<string, number>;
  transaction_count: number;
  upcoming_bills: Array<{
    name: string;
    amount: number;
    due_date: string;
  }>;
}

export interface WeekComparison {
  total_income_pct_change: number;
  total_expenses_pct_change: number;
  net_flow_pct_change: number;
}

/**
 * 获取每周财务摘要
 * @param weekStart 周开始日期 (YYYY-MM-DD)，默认本周一
 */
export async function getWeeklySummary(weekStart?: string): Promise<WeeklyDigestSummary> {
  const params = new URLSearchParams();
  if (weekStart) {
    params.set('week', weekStart);
  }

  const queryString = params.toString();
  const response = await apiClient.get(
    `/weekly-digest/weekly-summary${queryString ? `?${queryString}` : ''}`
  );
  return response.data;
}

/**
 * 发送周摘要邮件
 * @param weekStart 周开始日期 (YYYY-MM-DD)
 */
export async function sendSummaryEmail(weekStart?: string): Promise<{
  sent: boolean;
  reason?: string;
  recipient?: string;
  summary: WeeklyDigestSummary;
}> {
  const response = await apiClient.post('/weekly-digest/weekly-summary/send-email', {
    week: weekStart,
  });
  return response.data;
}
