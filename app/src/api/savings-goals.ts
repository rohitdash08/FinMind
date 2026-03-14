import { api } from './client';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  target_date: string | null;
  icon: string;
  active: boolean;
  progress_pct: number;
  milestones_achieved: number[];
  created_at: string | null;
};

export type SavingsGoalCreate = {
  name: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  target_date?: string | null;
  icon?: string;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate> & { active?: boolean };

export type Contribution = {
  id: number;
  amount: number;
  notes: string | null;
  contributed_at: string;
};

export type ContributeResponse = {
  contribution: Contribution;
  goal: SavingsGoal;
  new_milestones: number[];
};

export type WithdrawResponse = {
  contribution: Contribution;
  goal: SavingsGoal;
};

export async function listSavingsGoals(params?: {
  include_completed?: boolean;
}): Promise<SavingsGoal[]> {
  const qs = new URLSearchParams();
  if (params?.include_completed) qs.set('include_completed', 'true');
  const path = '/savings-goals' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<SavingsGoal[]>(path);
}

export async function getSavingsGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`);
}

export async function createSavingsGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings-goals', { method: 'POST', body: payload });
}

export async function updateSavingsGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteSavingsGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings-goals/${id}`, { method: 'DELETE' });
}

export async function addContribution(
  goalId: number,
  payload: { amount: number; notes?: string; contributed_at?: string },
): Promise<ContributeResponse> {
  return api<ContributeResponse>(`/savings-goals/${goalId}/contribute`, {
    method: 'POST',
    body: payload,
  });
}

export async function withdrawFromGoal(
  goalId: number,
  payload: { amount: number; notes?: string },
): Promise<WithdrawResponse> {
  return api<WithdrawResponse>(`/savings-goals/${goalId}/withdraw`, {
    method: 'POST',
    body: payload,
  });
}

export async function listContributions(goalId: number): Promise<Contribution[]> {
  return api<Contribution[]>(`/savings-goals/${goalId}/contributions`);
}
