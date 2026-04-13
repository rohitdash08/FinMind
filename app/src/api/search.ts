import { api } from './client';

export type SearchExpense = {
  id: number; type: 'expense'; amount: number; currency: string;
  description: string; category_id: number | null; expense_type: string; date: string;
};

export type SearchBill = {
  id: number; type: 'bill'; amount: number; currency: string;
  name: string; next_due_date: string; cadence: string | null;
};

export type SearchResult = {
  expenses: SearchExpense[];
  bills: SearchBill[];
  total: number;
};

export async function search(params: {
  q?: string; min_amount?: number; max_amount?: number;
  category_id?: number; expense_type?: string;
  from_date?: string; to_date?: string; source?: 'all' | 'expenses' | 'bills';
}): Promise<SearchResult> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)); });
  return api<SearchResult>('/search?' + qs.toString());
}
