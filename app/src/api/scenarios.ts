import { api } from './client';
export type SimResult = { baseline: { monthly_income: number; monthly_expenses: number }; projection: { month: number; income: number; expenses: number; net: number; cumulative: number }[]; summary: { total_saved: number; months: number } };
export async function simulate(params: { months?: number; income_change_pct?: number; expense_change_pct?: number; one_time_expense?: number; one_time_income?: number; savings_rate?: number }): Promise<SimResult> { return api('/scenarios/simulate', { method: 'POST', body: params }); }
