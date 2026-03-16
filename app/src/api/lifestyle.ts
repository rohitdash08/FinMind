import api from "./index";

export interface InflationTrend {
  month: string;
  amount: number;
}

export interface InflatedCategory {
  category_id: number;
  category_name: string;
  recent_avg_monthly: number;
  previous_avg_monthly: number;
  pct_change: number;
  abs_change_monthly: number;
  annualised_extra: number;
  trend: InflationTrend[];
}

export interface LifestyleInflationSummary {
  inflated_count: number;
  stable_count: number;
  total_extra_monthly_spend: number;
  total_extra_annual_spend: number;
}

export interface LifestyleInflationData {
  inflated_categories: InflatedCategory[];
  stable_categories: InflatedCategory[];
  summary: LifestyleInflationSummary;
  window_months: number;
  inflation_threshold_pct: number;
}

export async function getLifestyleInflation(
  windowMonths = 3,
  thresholdPct = 10
): Promise<LifestyleInflationData> {
  const { data } = await api.get<LifestyleInflationData>(
    "/insights/lifestyle-inflation",
    { params: { window_months: windowMonths, threshold_pct: thresholdPct } }
  );
  return data;
}
