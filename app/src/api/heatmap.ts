/**
 * Calendar Heatmap API client.
 */

export interface HeatmapDay {
  date: string;
  amount: number;
  count: number;
  intensity: 0 | 1 | 2 | 3 | 4;
}

export interface HeatmapData {
  year: number;
  month: number | null;
  start_date: string;
  end_date: string;
  total_spending: number;
  total_transactions: number;
  active_days: number;
  max_daily: number;
  avg_daily: number;
  current_streak: number;
  days: HeatmapDay[];
}

export async function fetchHeatmap(year: number, month?: number | null): Promise<HeatmapData> {
  let url = `/heatmap?year=${year}`;
  if (month != null) url += `&month=${month}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
  });
  if (!res.ok) throw new Error("Failed to fetch heatmap data");
  return res.json();
}
