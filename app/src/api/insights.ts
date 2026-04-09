import { api } from '@/api/index';
import { API_BASE_URL } from '@/config';

export interface HeatmapDataPoint {
  date: string; // YYYY-MM-DD
  total_amount: number;
}

export interface GetSpendingHeatmapParams {
  startDate: string; // YYYY-MM-DD
  endDate: string; // YYYY-MM-DD
}

export const getSpendingHeatmap = async (
  params: GetSpendingHeatmapParams,
): Promise<HeatmapDataPoint[]> => {
  const queryParams = new URLSearchParams({
    start_date: params.startDate,
    end_date: params.endDate,
  }).toString();

  const response = await api.get<HeatmapDataPoint[]>(
    `${API_BASE_URL}/insights/spending-heatmap?${queryParams}`,
  );
  return response.data;
};
