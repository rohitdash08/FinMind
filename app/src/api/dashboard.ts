import { api } from './client';

// ---------------------------------------------------------------------------
// Dashboard widget preferences
// ---------------------------------------------------------------------------

export const WIDGET_IDS = [
  'summary_cards',
  'recent_transactions',
  'upcoming_bills',
  'category_breakdown',
] as const;

export type WidgetId = (typeof WIDGET_IDS)[number];

export type WidgetConfig = {
  id: WidgetId;
  label: string;
  visible: boolean;
};

export type DashboardPreferences = {
  widgets: WidgetConfig[];
};

export const DEFAULT_WIDGETS: WidgetConfig[] = [
  { id: 'summary_cards', label: 'Summary Cards', visible: true },
  { id: 'recent_transactions', label: 'Recent Transactions', visible: true },
  { id: 'upcoming_bills', label: 'Upcoming Bills', visible: true },
  { id: 'category_breakdown', label: 'Category Breakdown', visible: true },
];

export async function getDashboardPreferences(): Promise<DashboardPreferences> {
  return api<DashboardPreferences>('/dashboard/preferences');
}

export async function updateDashboardPreferences(
  widgets: WidgetConfig[],
): Promise<DashboardPreferences> {
  return api<DashboardPreferences>('/dashboard/preferences', {
    method: 'PUT',
    body: { widgets },
  });
}

export type DashboardSummary = {
  period: { month: string };
  summary: {
    net_flow: number;
    monthly_income: number;
    monthly_expenses: number;
    upcoming_bills_total: number;
    upcoming_bills_count: number;
  };
  recent_transactions: Array<{
    id: number;
    description: string;
    amount: number;
    date: string;
    type: 'INCOME' | 'EXPENSE' | string;
    category_id: number | null;
    currency: string;
  }>;
  upcoming_bills: Array<{
    id: number;
    name: string;
    amount: number;
    currency: string;
    next_due_date: string;
    cadence: string;
    channel_email: boolean;
    channel_whatsapp: boolean;
  }>;
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    share_pct: number;
  }>;
  errors?: string[];
};

export async function getDashboardSummary(month?: string): Promise<DashboardSummary> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<DashboardSummary>(`/dashboard/summary${query}`);
}
