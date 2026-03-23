import { api } from './client';

export type Milestone = {
  percentage: number;
  reached: boolean;
};

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  status: 'ACTIVE' | 'COMPLETED' | 'CANCELLED';
  progress: number;
  milestones: Milestone[];
  created_at: string | null;
};

export type SavingsGoalCreate = {
  name: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string | null;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate> & {
  status?: 'ACTIVE' | 'COMPLETED' | 'CANCELLED';
};

export async function listSavingsGoals(status?: string): Promise<SavingsGoal[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return api<SavingsGoal[]>(`/savings-goals${qs}`);
}

export async function getSavingsGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`);
}

export async function createSavingsGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings-goals', { method: 'POST', body: payload });
}

export async function updateSavingsGoal(
  id: number,
  payload: SavingsGoalUpdate,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`, { method: 'PATCH', body: payload });
}

export async function depositToGoal(
  id: number,
  amount: number,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}/deposit`, {
    method: 'POST',
    body: { amount },
  });
}

export async function withdrawFromGoal(
  id: number,
  amount: number,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}/withdraw`, {
    method: 'POST',
    body: { amount },
  });
}

export async function deleteSavingsGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings-goals/${id}`, { method: 'DELETE' });
}
