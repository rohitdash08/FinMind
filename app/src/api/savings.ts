import { api } from './client';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  target_date: string | null;
  color: string;
  active: boolean;
  progress: number;
  created_at: string | null;
};

export type SavingsGoalCreate = {
  name: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  target_date?: string;
  color?: string;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate> & { active?: boolean };

export type Contribution = {
  id: number;
  amount: number;
  notes: string | null;
  contributed_at: string;
};

export type ContributePayload = {
  amount: number;
  notes?: string;
  contributed_at?: string;
};

export type ContributeResponse = {
  contribution: Contribution;
  goal: SavingsGoal;
};

export async function listGoals(active = true): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>(`/savings?active=${active}`);
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`);
}

export async function createGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings', { method: 'POST', body: payload });
}

export async function updateGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings/${id}`, { method: 'DELETE' });
}

export async function listContributions(goalId: number): Promise<Contribution[]> {
  return api<Contribution[]>(`/savings/${goalId}/contributions`);
}

export async function addContribution(
  goalId: number,
  payload: ContributePayload,
): Promise<ContributeResponse> {
  return api<ContributeResponse>(`/savings/${goalId}/contribute`, {
    method: 'POST',
    body: payload,
  });
}
