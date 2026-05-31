import { api } from './client';

export type SearchResult = {
  transactions: SearchTransaction[];
  bills: SearchBill[];
  total_count: number;
};

export type SearchTransaction = {
  id: number;
  type: 'expense';
  description: string;
  amount: number;
  date: string;
  expense_type: string;
  category_id: number | null;
  currency: string;
};

export type SearchBill = {
  id: number;
  type: 'bill';
  name: string;
  amount: number;
  next_due_date: string;
  cadence: string;
  currency: string;
};

export type SearchParams = {
  q?: string;
  from?: string;
  to?: string;
  category_id?: number;
  amount_min?: number;
  amount_max?: number;
  type?: 'all' | 'transactions' | 'bills';
  page?: number;
  page_size?: number;
};

export type SavedSearch = {
  id: string;
  name: string;
  params: SearchParams;
  created_at: string;
};

export async function search(params: SearchParams): Promise<SearchResult> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  });
  return api<SearchResult>(`/search?${qs.toString()}`);
}

export function getSavedSearches(): SavedSearch[] {
  try {
    return JSON.parse(localStorage.getItem('finmind-saved-searches') || '[]');
  } catch {
    return [];
  }
}

export function saveSearch(name: string, params: SearchParams): SavedSearch[] {
  const searches = getSavedSearches();
  const entry: SavedSearch = {
    id: `saved-${Date.now()}`,
    name,
    params,
    created_at: new Date().toISOString(),
  };
  searches.push(entry);
  localStorage.setItem('finmind-saved-searches', JSON.stringify(searches));
  return searches;
}

export function deleteSavedSearch(id: string): SavedSearch[] {
  const searches = getSavedSearches().filter((s) => s.id !== id);
  localStorage.setItem('finmind-saved-searches', JSON.stringify(searches));
  return searches;
}
