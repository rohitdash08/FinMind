import { api } from './client';

export type MetricDetail = Record<string, number | string | null | undefined>;

export type Metric = {
  points: number;
  max: number;
  detail?: MetricDetail;
};

export type HealthScoreBreakdown = {
  savings_rate: Metric;
  spending_stability: Metric;
  bill_reliability: Metric;
  trend: Metric;
};

export type HealthScore = {
  score: number;
  grade: string;
  computed_at: string;
  period: string;
  breakdown: HealthScoreBreakdown;
};

export type HealthScoreHistoryItem = {
  period: string;
  score: number;
  grade: string;
  breakdown: {
    savings_rate_pts: number;
    spending_stability_pts: number;
    bill_reliability_pts: number;
    trend_pts: number;
  };
};

export type HealthScoreHistory = {
  history: HealthScoreHistoryItem[];
};

export type HealthScoreTips = {
  tips: string[];
  count: number;
};

export async function getHealthScore(): Promise<HealthScore> {
  return api<HealthScore>('/health-score');
}

export async function getHealthScoreHistory(): Promise<HealthScoreHistory> {
  return api<HealthScoreHistory>('/health-score/history');
}

export async function getHealthScoreTips(): Promise<HealthScoreTips> {
  return api<HealthScoreTips>('/health-score/tips');
}
