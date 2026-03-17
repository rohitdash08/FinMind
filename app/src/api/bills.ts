import { api } from './client';

export type Bill = {
  id: number;
  name: string;
  amount: number;
  currency?: string;
  next_due_date?: string; // YYYY-MM-DD
  cadence?: 'WEEKLY' | 'MONTHLY' | 'YEARLY' | 'ONCE';
  autopay_enabled?: boolean;
  channel_email?: boolean;
  channel_whatsapp?: boolean;
  paid_at?: string | null;
};

export type BillCreate = Partial<Bill> & { name: string; amount: number };
export type BillUpdate = Partial<BillCreate>;

export async function listBills(params?: {
  from?: string;
  to?: string;
  status?: string;
  category_id?: number;
  page?: number;
  page_size?: number;
}): Promise<Bill[]> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
  }
  const path = '/bills' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<Bill[]>(path);
}

export async function createBill(payload: BillCreate): Promise<Bill> {
  return api<Bill>('/bills', { method: 'POST', body: payload });
}

export async function updateBill(id: number, payload: BillUpdate): Promise<Bill> {
  return api<Bill>(`/bills/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteBill(id: number): Promise<{ message?: string } | { message: string }> {
  return api(`/bills/${id}`, { method: 'DELETE' });
}

export async function markBillPaid(id: number): Promise<{ message: string } | Bill> {
  // OpenAPI shows /bills/{billId}/pay
  return api(`/bills/${id}/pay`, { method: 'POST' });
}
