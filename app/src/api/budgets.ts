import api from "./index";

export interface CategoryBudget {
  id: number;
  category_id: number;
  month?: string;
  budget_limit: number;
  warning_threshold_pct: number;
  created_at: string;
}

export interface OverspendWarning {
  budget_id: number;
  category_id: number;
  category_name: string | null;
  month: string;
  budget_limit: number;
  spent: number;
  remaining: number;
  pct_used: number;
  warning_threshold_pct: number;
  warning_level: "CRITICAL" | "HIGH" | "MEDIUM" | "OK";
  is_over_budget: boolean;
}

export interface OverspendReport {
  month: string;
  warnings: OverspendWarning[];
  summary: {
    critical: number;
    high: number;
    medium: number;
    ok: number;
    total: number;
  };
}

export interface CreateBudgetPayload {
  category_id: number;
  budget_limit: number;
  month?: string;
  warning_threshold_pct?: number;
}

export const getBudgets = (): Promise<CategoryBudget[]> =>
  api.get("/budgets").then((r) => r.data);

export const createBudget = (p: CreateBudgetPayload): Promise<CategoryBudget> =>
  api.post("/budgets", p).then((r) => r.data);

export const updateBudget = (
  id: number,
  p: Partial<CreateBudgetPayload>
): Promise<CategoryBudget> =>
  api.patch(`/budgets/${id}`, p).then((r) => r.data);

export const deleteBudget = (id: number): Promise<void> =>
  api.delete(`/budgets/${id}`).then((r) => r.data);

export const getOverspendWarnings = (
  month?: string,
  onlyWarnings = false
): Promise<OverspendReport> => {
  const params = new URLSearchParams();
  if (month) params.set("month", month);
  if (onlyWarnings) params.set("only_warnings", "true");
  return api.get(`/budgets/overspend?${params}`).then((r) => r.data);
};
