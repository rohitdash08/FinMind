import { getDashboardSummary, type DashboardSummary } from './dashboard';
import { getBudgetSuggestion, type BudgetSuggestion } from './insights';

export type WeeklyDigestTrend = {
  label: string;
  value: string;
  tone: 'positive' | 'negative' | 'neutral';
};

export type WeeklyDigest = {
  weekStart: string;
  weekEnd: string;
  generatedAt: string;
  headline: string;
  summary: string;
  trends: WeeklyDigestTrend[];
  insights: string[];
  actionItems: string[];
};

function formatMoney(value: number, currency = 'USD') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(value) ? value : 0);
}

function addDays(date: Date, days: number) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function getWeekWindow(anchor = new Date()) {
  const date = new Date(anchor);
  const day = date.getDay();
  const diffToMonday = (day + 6) % 7;
  const start = addDays(date, -diffToMonday);
  const end = addDays(start, 6);
  return { start: isoDate(start), end: isoDate(end) };
}

function pickCurrency(dashboard: DashboardSummary) {
  return (
    dashboard.recent_transactions[0]?.currency ||
    dashboard.upcoming_bills[0]?.currency ||
    'USD'
  );
}

export function buildWeeklyDigest(
  dashboard: DashboardSummary,
  budget: BudgetSuggestion,
  anchor = new Date(),
): WeeklyDigest {
  const { start, end } = getWeekWindow(anchor);
  const currency = pickCurrency(dashboard);
  const netFlow = dashboard.summary.net_flow;
  const expenses = dashboard.summary.monthly_expenses;
  const upcomingBills = dashboard.summary.upcoming_bills_total;
  const mom = budget.analytics.month_over_month_change_pct;
  const topCategory = dashboard.category_breakdown[0];
  const topCategoryLabel = topCategory
    ? `${topCategory.category_name} leads spending at ${formatMoney(topCategory.amount, currency)} (${topCategory.share_pct.toFixed(1)}%).`
    : 'No category has dominated spending yet.';

  const headline = netFlow >= 0
    ? `Positive net flow of ${formatMoney(netFlow, currency)} this week`
    : `Net flow is down ${formatMoney(Math.abs(netFlow), currency)} this week`;

  const tips = budget.tips?.filter(Boolean) ?? [];
  const insights = [
    topCategoryLabel,
    `Month-over-month expense movement is ${mom.toFixed(2)}%.`,
    ...tips.slice(0, 3),
  ];

  const actionItems = [
    upcomingBills > 0
      ? `Review ${dashboard.summary.upcoming_bills_count} upcoming bill(s) totaling ${formatMoney(upcomingBills, currency)}.`
      : 'No upcoming bills are due soon; keep the buffer intact.',
    expenses > budget.suggested_total
      ? `Spending is above the suggested budget by ${formatMoney(expenses - budget.suggested_total, currency)}; trim one flexible category.`
      : `Spending is within the suggested budget by ${formatMoney(budget.suggested_total - expenses, currency)}; keep the current pace.`,
    'Export or screenshot this digest for a weekly money check-in.',
  ];

  return {
    weekStart: start,
    weekEnd: end,
    generatedAt: new Date().toISOString(),
    headline,
    summary: `From ${start} to ${end}, FinMind reviewed cash flow, bills, category concentration, and AI budget guidance to create this weekly digest.`,
    trends: [
      { label: 'Net flow', value: formatMoney(netFlow, currency), tone: netFlow >= 0 ? 'positive' : 'negative' },
      { label: 'Monthly expenses', value: formatMoney(expenses, currency), tone: expenses <= budget.suggested_total ? 'positive' : 'negative' },
      { label: 'Suggested budget', value: formatMoney(budget.suggested_total, currency), tone: 'neutral' },
      { label: 'Upcoming bills', value: formatMoney(upcomingBills, currency), tone: upcomingBills > 0 ? 'negative' : 'positive' },
    ],
    insights,
    actionItems,
  };
}

export async function getWeeklyDigest(params?: {
  month?: string;
  persona?: string;
  geminiApiKey?: string;
  anchorDate?: Date;
}): Promise<WeeklyDigest> {
  const [dashboard, budget] = await Promise.all([
    getDashboardSummary(params?.month),
    getBudgetSuggestion({
      month: params?.month,
      persona: params?.persona,
      geminiApiKey: params?.geminiApiKey,
    }),
  ]);
  return buildWeeklyDigest(dashboard, budget, params?.anchorDate);
}
