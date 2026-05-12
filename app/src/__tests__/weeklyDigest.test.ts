import { buildWeeklyDigest } from '@/api/weeklyDigest';
import type { DashboardSummary } from '@/api/dashboard';
import type { BudgetSuggestion } from '@/api/insights';

const dashboard: DashboardSummary = {
  period: { month: '2026-02' },
  summary: {
    net_flow: 450,
    monthly_income: 2000,
    monthly_expenses: 1550,
    upcoming_bills_total: 120,
    upcoming_bills_count: 2,
  },
  recent_transactions: [
    {
      id: 1,
      description: 'Salary',
      amount: 2000,
      date: '2026-02-10',
      type: 'INCOME',
      category_id: null,
      currency: 'USD',
    },
  ],
  upcoming_bills: [],
  category_breakdown: [
    { category_id: 1, category_name: 'Food', amount: 500, share_pct: 32.25 },
  ],
  errors: [],
};

const budget: BudgetSuggestion = {
  month: '2026-02',
  suggested_total: 1600,
  breakdown: { needs: 800, wants: 480, savings: 320 },
  tips: ['Pack lunch twice this week'],
  analytics: {
    month_over_month_change_pct: -4.5,
    current_month_expenses: 1550,
    previous_month_expenses: 1623,
    top_categories: [],
  },
  method: 'heuristic',
};

describe('buildWeeklyDigest', () => {
  it('generates a narrative digest with trends and action items', () => {
    const digest = buildWeeklyDigest(dashboard, budget, new Date('2026-02-11T12:00:00Z'));

    expect(digest.weekStart).toBe('2026-02-09');
    expect(digest.weekEnd).toBe('2026-02-15');
    expect(digest.headline).toContain('Positive net flow');
    expect(digest.trends).toHaveLength(4);
    expect(digest.insights.join(' ')).toContain('Food leads spending');
    expect(digest.actionItems.join(' ')).toContain('upcoming bill');
  });
});
