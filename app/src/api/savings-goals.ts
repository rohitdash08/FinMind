import { apiClient } from './client';

export interface SavingsGoal {
  id: string;
  name: string;
  targetAmount: number;
  currentAmount: number;
  deadline: string;
  monthlyContribution: number;
  category: string;
  color: string;
  createdAt: string;
  updatedAt: string;
}

export interface SavingsMilestone {
  id: string;
  goalId: string;
  percentage: number;
  reachedAt: string;
  amount: number;
}

export interface CreateSavingsGoalRequest {
  name: string;
  targetAmount: number;
  currentAmount?: number;
  deadline: string;
  monthlyContribution: number;
  category: string;
  color?: string;
}

export interface UpdateSavingsGoalRequest {
  name?: string;
  targetAmount?: number;
  currentAmount?: number;
  deadline?: string;
  monthlyContribution?: number;
  category?: string;
  color?: string;
}

export const getSavingsGoals = async (): Promise<SavingsGoal[]> => {
  const response = await apiClient.get('/savings-goals');
  return response.data;
};

export const getSavingsGoal = async (id: string): Promise<SavingsGoal> => {
  const response = await apiClient.get(`/savings-goals/${id}`);
  return response.data;
};

export const createSavingsGoal = async (data: CreateSavingsGoalRequest): Promise<SavingsGoal> => {
  const response = await apiClient.post('/savings-goals', data);
  return response.data;
};

export const updateSavingsGoal = async (id: string, data: UpdateSavingsGoalRequest): Promise<SavingsGoal> => {
  const response = await apiClient.put(`/savings-goals/${id}`, data);
  return response.data;
};

export const deleteSavingsGoal = async (id: string): Promise<void> => {
  await apiClient.delete(`/savings-goals/${id}`);
};

export const contributeToGoal = async (id: string, amount: number): Promise<SavingsGoal> => {
  const response = await apiClient.post(`/savings-goals/${id}/contribute`, { amount });
  return response.data;
};

export const getGoalMilestones = async (goalId: string): Promise<SavingsMilestone[]> => {
  const response = await apiClient.get(`/savings-goals/${goalId}/milestones`);
  return response.data;
};

export const getSavingsGoalsSummary = async (): Promise<{
  totalSaved: number;
  totalTarget: number;
  goalsOnTrack: number;
  goalsBehind: number;
  monthlyTotal: number;
}> => {
  const response = await apiClient.get('/savings-goals/summary');
  return response.data;
};
