import { api } from "./client";

export interface DigestCategory {
  category_id: number;
  category_name: string;
  amount: number;
}

export interface DigestWeek {
  week_start: string;
  week_end: string;
  total: number;
  delta_percent: number | null;
  trend: "up" | "down" | "flat";
  categories: DigestCategory[];
}

export interface WeeklyDigestResponse {
  period: {
    start_date: string;
    end_date: string;
    weeks: number;
  };
  summary: {
    current_week_total: number;
    previous_weeks_total: number;
    current_week: string | null;
  };
  weeks: DigestWeek[];
  top_categories: DigestCategory[];
  upcoming_bills: {
    id: number;
    name: string;
    amount: number;
    currency: string;
    next_due_date: string;
  }[];
}

export const getWeeklyDigest = async (weeks: number = 4): Promise<WeeklyDigestResponse> => {
  return api<WeeklyDigestResponse>(`/digest/weekly?weeks=${weeks}`);
};