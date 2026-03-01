import { api } from './client';

export type CategoryBreakdown = {
  category_id: number | null;
  category_name: string;
  total: number;
};

export type WeeklyDigest = {
  period: { start: string; end: string };
  summary: {
    total_income: number;
    total_expenses: number;
    net_flow: number;
  };
  category_breakdown: CategoryBreakdown[];
  trends: {
    spending_change_pct: number;
    direction: 'up' | 'down' | 'flat';
    current_week_total: number;
    previous_week_total: number;
  };
  upcoming_bills: Array<{
    id: number;
    name: string;
    amount: number;
    currency: string;
    next_due_date: string;
    cadence: string;
  }>;
  upcoming_bills_total: number;
  generated_at: string;
  ai_insights?: {
    highlights: string[];
    tip?: string;
  };
};

export type DigestSendResult = {
  digest: WeeklyDigest;
  delivery: Record<string, string>;
};

export async function getWeeklyDigest(refDate?: string): Promise<WeeklyDigest> {
  const q = refDate ? `?ref_date=${encodeURIComponent(refDate)}` : '';
  return api<WeeklyDigest>(`/digest/weekly${q}`);
}

export async function sendWeeklyDigest(opts?: {
  refDate?: string;
  email?: boolean;
  whatsapp?: string;
}): Promise<DigestSendResult> {
  return api<DigestSendResult>('/digest/weekly/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref_date: opts?.refDate,
      email: opts?.email ?? true,
      whatsapp: opts?.whatsapp,
    }),
  });
}
