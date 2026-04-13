import { api } from './client';
export type OptResult = { total_income: number; total_expenses: number; savings_potential: number; categories: { name: string; current_spend: number; suggested_budget: number; change_pct: number }[]; recommendations: string[] };
export async function optimizeBudget(): Promise<OptResult> { return api('/budget/optimize'); }
