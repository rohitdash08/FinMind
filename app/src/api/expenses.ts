import { api, baseURL } from './client';

export type Expense = {
  id: number;
  amount: number;
  currency?: string;
  description: string;
  category_id: number | null;
  date: string; // ISO date
};

export type ExpenseCreate = {
  amount: number;
  description: string;
  category_id?: number | null;
  date: string; // ISO date
};

export type ExpenseUpdate = Partial<ExpenseCreate>;

export type ImportTransaction = {
  date: string;
  amount: number;
  description: string;
  category_id?: number | null;
  currency?: string;
};

export type ImportPreviewResponse = {
  total: number;
  duplicates: number;
  transactions: ImportTransaction[];
};

export type RecurringExpense = {
  id: number;
  amount: number;
  currency: string;
  expense_type: string;
  category_id: number | null;
  description: string;
  cadence: 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY';
  start_date: string;
  end_date: string | null;
  active: boolean;
};

export type RecurringExpenseCreate = {
  amount: number;
  description: string;
  category_id?: number | null;
  cadence: 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY';
  start_date: string;
  end_date?: string | null;
  expense_type?: 'EXPENSE' | 'INCOME';
  currency?: string;
};

export async function listExpenses(params?: {
  from?: string;
  to?: string;
  category_id?: number;
  search?: string;
  page?: number;
  page_size?: number;
}): Promise<Expense[]> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
  }
  const path = '/expenses' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<Expense[]>(path);
}

export async function createExpense(payload: ExpenseCreate): Promise<Expense> {
  return api<Expense>('/expenses', { method: 'POST', body: payload });
}

export async function updateExpense(id: number, payload: ExpenseUpdate): Promise<Expense> {
  return api<Expense>(`/expenses/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteExpense(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/expenses/${id}`, { method: 'DELETE' });
}

export async function previewExpenseImport(file: File): Promise<ImportPreviewResponse> {
  const token = localStorage.getItem('fm_token');
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${baseURL}/expenses/import/preview`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
    credentials: 'include',
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const payload = await res.json();
      message = payload?.error || payload?.message || message;
    } catch {
      // noop
    }
    throw new Error(message);
  }
  return res.json() as Promise<ImportPreviewResponse>;
}

export async function commitExpenseImport(
  transactions: ImportTransaction[],
): Promise<{ inserted: number; duplicates: number }> {
  return api<{ inserted: number; duplicates: number }>('/expenses/import/commit', {
    method: 'POST',
    body: { transactions },
  });
}

export async function listRecurringExpenses(): Promise<RecurringExpense[]> {
  return api<RecurringExpense[]>('/expenses/recurring');
}

export async function createRecurringExpense(
  payload: RecurringExpenseCreate,
): Promise<RecurringExpense> {
  return api<RecurringExpense>('/expenses/recurring', { method: 'POST', body: payload });
}

export async function generateRecurringExpenses(
  recurringId: number,
  throughDate: string,
): Promise<{ inserted: number }> {
  return api<{ inserted: number }>(`/expenses/recurring/${recurringId}/generate`, {
    method: 'POST',
    body: { through_date: throughDate },
  });
}
