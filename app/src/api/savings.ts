import { api } from './client';

export type SavingsGoal = {
  id: number;
  title: string;
  target: number;
  current: number;
  currency: string;
  deadline: string | null;
  monthlyTarget: number;
  status: 'on-track' | 'ahead' | 'behind' | 'completed';
  created_at?: string;
};

export type SavingsGoalCreate = {
  title: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string | null;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate>;

export async function listSavingsGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings');
}

export async function createSavingsGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings', { method: 'POST', body: payload });
}

export async function getSavingsGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`);
}

export async function updateSavingsGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`, { method: 'PATCH', body: payload });
}

export async function contributeSavingsGoal(id: number, amount: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}/contribute`, { method: 'POST', body: { amount } });
}

export async function deleteSavingsGoal(id: number): Promise<{ message: string }> {
  return api(`/savings/${id}`, { method: 'DELETE' });
}
