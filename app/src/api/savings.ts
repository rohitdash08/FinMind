import { api } from './client';

export type SavingsGoalStatus = 'ACTIVE' | 'COMPLETED' | 'CANCELLED';

export type SavingsGoal = {
  id: number;
  name: string;
  description?: string | null;
  target_amount: number;
  current_amount: number;
  currency: string;
  target_date?: string | null;
  icon: string;
  color: string;
  status: SavingsGoalStatus;
  progress_pct: number;
  remaining: number;
  days_remaining?: number;
  monthly_needed?: number;
  created_at?: string;
  updated_at?: string;
  contributions?: SavingsContribution[];
};

export type SavingsContribution = {
  id: number;
  goal_id: number;
  amount: number;
  note?: string | null;
  contributed_at?: string;
  created_at?: string;
};

export type SavingsGoalCreate = {
  name: string;
  description?: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  target_date?: string;
  icon?: string;
  color?: string;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate> & {
  status?: SavingsGoalStatus;
};

export type SavingsSummary = {
  total_goals: number;
  active_goals: number;
  completed_goals: number;
  total_saved: number;
  total_target: number;
  overall_progress_pct: number;
};

export async function listSavingsGoals(
  status?: string,
): Promise<SavingsGoal[]> {
  const qs = new URLSearchParams();
  if (status) qs.set('status', status);
  const path = '/savings' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<SavingsGoal[]>(path);
}

export async function getSavingsGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`);
}

export async function createSavingsGoal(
  payload: SavingsGoalCreate,
): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings', { method: 'POST', body: payload });
}

export async function updateSavingsGoal(
  id: number,
  payload: SavingsGoalUpdate,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteSavingsGoal(
  id: number,
): Promise<{ message: string }> {
  return api(`/savings/${id}`, { method: 'DELETE' });
}

export async function addContribution(
  goalId: number,
  payload: { amount: number; note?: string; contributed_at?: string },
): Promise<{ contribution: SavingsContribution; goal: SavingsGoal }> {
  return api(`/savings/${goalId}/contributions`, {
    method: 'POST',
    body: payload,
  });
}

export async function withdrawFromGoal(
  goalId: number,
  payload: { amount: number; note?: string },
): Promise<{ contribution: SavingsContribution; goal: SavingsGoal }> {
  return api(`/savings/${goalId}/withdraw`, {
    method: 'POST',
    body: payload,
  });
}

export async function getSavingsSummary(): Promise<SavingsSummary> {
  return api<SavingsSummary>('/savings/summary');
}
