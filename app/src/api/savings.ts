import api from "./index";

export type OpportunityType =
  | "consistent_underspend"
  | "recurring_subscription"
  | "irregular_big_spend";

export interface SavingsOpportunity {
  type: OpportunityType;
  category_id: number;
  category_name: string;
  message: string;
  // consistent_underspend
  avg_monthly_spend?: number;
  recent_spend?: number;
  reduction_pct?: number;
  estimated_monthly_saving?: number;
  // recurring_subscription
  recurring_amount?: number;
  months_detected?: string[];
  estimated_annual_cost?: number;
  // irregular_big_spend
  amount?: number;
  category_avg?: number;
  spent_at?: string;
  notes?: string;
}

export interface TopSpenderCategory {
  type: "top_spender";
  category_id: number;
  category_name: string;
  avg_monthly_spend: number;
  pct_of_total_spend: number;
  message: string;
}

export interface SavingsReport {
  months_analysed: number;
  total_estimated_monthly_saving: number;
  opportunities: SavingsOpportunity[];
  top_spender_categories: TopSpenderCategory[];
  summary: {
    consistent_underspend: number;
    recurring_subscriptions: number;
    irregular_big_spends: number;
    total_opportunities: number;
  };
}

export const getSavingsOpportunities = (months = 3): Promise<SavingsReport> =>
  api.get(`/insights/savings-opportunities?months=${months}`).then((r) => r.data);
