import { api } from './client';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  achieved: boolean;
  progress_pct: number;
  created_at: string;
};

export type SavingsGoalDetail = SavingsGoal & {
  contributions: Array<{
    id: number;
    amount: number;
    notes: string | null;
    created_at: string;
  }>;
};

export type ContributeResult = SavingsGoal & {
  contribution: { id: number; amount: number; notes: string | null; created_at: string };
  milestone_reached: boolean;
};

export async function listGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/goals');
}

export async function createGoal(data: {
  name: string;
  target_amount: number;
  currency?: string;
  deadline?: string;
}): Promise<SavingsGoal> {
  return api<SavingsGoal>('/goals', { method: 'POST', body: data });
}

export async function getGoal(id: number): Promise<SavingsGoalDetail> {
  return api<SavingsGoalDetail>(`/goals/${id}`);
}

export async function updateGoal(
  id: number,
  data: { name?: string; target_amount?: number; deadline?: string | null },
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`, { method: 'PATCH', body: data });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/goals/${id}`, { method: 'DELETE' });
}

export async function contribute(
  goalId: number,
  data: { amount: number; notes?: string },
): Promise<ContributeResult> {
  return api<ContributeResult>(`/goals/${goalId}/contribute`, {
    method: 'POST',
    body: data,
  });
}
