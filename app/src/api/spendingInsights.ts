import { api } from './client';

export type SpendingInsight = {
  type: 'spike' | 'drop' | 'concentration' | 'new_category';
  category_id: number | null;
  category_name: string;
  change_pct?: number;
  concentration_pct?: number;
  explanation: string;
};

export type CategorySpending = {
  category_id: number | null;
  category_name: string;
  current_total: number;
  previous_total: number;
  transaction_count: number;
  change_pct?: number | null;
};

export type SpendingInsightsResponse = {
  insights: SpendingInsight[];
  categories: CategorySpending[];
  total_spent: number;
  daily_average: number;
  period: {
    start: string;
    end: string;
    days: number;
  };
};

export async function getSpendingInsights(params?: {
  days?: number;
}): Promise<SpendingInsightsResponse> {
  const qs = params?.days ? `?days=${params.days}` : '';
  return api<SpendingInsightsResponse>(`/spending-insights${qs}`);
}
