import { api } from './client';

export type SpendingCategory = {
  category_id: number | null;
  category_name: string;
  total: number;
  transaction_count: number;
  classification: 'essential' | 'discretionary';
};

export type SpendingSplitResponse = {
  essential_total: number;
  discretionary_total: number;
  total: number;
  ratio: number | null;
  essential_pct: number;
  discretionary_pct: number;
  categories: SpendingCategory[];
  period: {
    start: string;
    end: string;
    days: number;
  };
};

export async function getSpendingSplit(params?: {
  days?: number;
}): Promise<SpendingSplitResponse> {
  const qs = params?.days ? `?days=${params.days}` : '';
  return api<SpendingSplitResponse>(`/spending-split${qs}`);
}
