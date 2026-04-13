import { api } from './client';
export type ForecastMonth = { month: number; period: string; projected_income: number; projected_expenses: number; known_bills: number; net_flow: number; cumulative_net: number; };
export type ForecastResult = { forecast: ForecastMonth[]; avg_daily_spend: number; avg_daily_income: number; avg_daily_net: number; data_period_days: number; upcoming_bills_count: number; };
export async function getForecast(months?: number): Promise<ForecastResult> { return api('/forecast' + (months ? '?months=' + months : '')); }
