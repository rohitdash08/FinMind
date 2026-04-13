import { api } from './client';

export type BudgetSuggestion = {
  category_id: number | null;
  category_name: string;
  monthly_average: number;
  suggested_budget: number;
  period_total: number;
  pct_of_spending?: number;
};

export type BudgetRule = {
  needs: number;
  wants: number;
  savings: number;
};

export type BudgetSuggestResponse = {
  suggestions: BudgetSuggestion[];
  monthly_income: number;
  estimated_monthly_income: number;
  monthly_expense: number;
  savings_target: number;
  budget_rule: BudgetRule;
  period: {
    start: string;
    end: string;
    days: number;
  };
};

export async function getBudgetSuggestions(): Promise<BudgetSuggestResponse> {
  return api<BudgetSuggestResponse>('/budget-suggest');
}
