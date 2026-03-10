import { api } from './client';

export type SavingsGoal = {
  id: number;
  name: string;
  description?: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline?: string; // ISO date
  created_at: string;
  updated_at: string;
};

export type SavingsGoalCreate = {
  name: string;
  description?: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate>;

export type GoalMilestone = {
  id: number;
  goal_id: number;
  name: string;
  target_percentage: number; // 0-100
  achieved: boolean;
  achieved_at?: string;
};

export type MilestoneCreate = {
  goal_id: number;
  name: string;
  target_percentage: number;
};

/**
 * List all savings goals for the current user
 */
export async function listSavingsGoals(params?: {
  active?: boolean;
  search?: string;
}): Promise<SavingsGoal[]> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
  }
  const path = '/savings-goals' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<SavingsGoal[]>(path);
}

/**
 * Get a single savings goal by ID
 */
export async function getSavingsGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`);
}

/**
 * Create a new savings goal
 */
export async function createSavingsGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings-goals', { method: 'POST', body: payload });
}

/**
 * Update an existing savings goal
 */
export async function updateSavingsGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`, { method: 'PATCH', body: payload });
}

/**
 * Delete a savings goal
 */
export async function deleteSavingsGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings-goals/${id}`, { method: 'DELETE' });
}

/**
 * Add funds to a savings goal
 */
export async function addToSavingsGoal(
  id: number,
  amount: number,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}/add`, {
    method: 'POST',
    body: { amount },
  });
}

/**
 * Withdraw funds from a savings goal
 */
export async function withdrawFromSavingsGoal(
  id: number,
  amount: number,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}/withdraw`, {
    method: 'POST',
    body: { amount },
  });
}

/**
 * List milestones for a savings goal
 */
export async function listMilestones(goalId: number): Promise<GoalMilestone[]> {
  return api<GoalMilestone[]>(`/savings-goals/${goalId}/milestones`);
}

/**
 * Create a milestone for a savings goal
 */
export async function createMilestone(payload: MilestoneCreate): Promise<GoalMilestone> {
  return api<GoalMilestone>('/savings-goals/milestones', { method: 'POST', body: payload });
}

/**
 * Delete a milestone
 */
export async function deleteMilestone(milestoneId: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings-goals/milestones/${milestoneId}`, { method: 'DELETE' });
}

/**
 * Get goal progress metrics
 */
export async function getGoalProgress(goalId: number): Promise<{
  percentage: number;
  remaining: number;
  days_left?: number;
  on_track: boolean;
  required_daily_saving?: number;
}> {
  return api(`/savings-goals/${goalId}/progress`);
}
