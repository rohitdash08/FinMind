import { api } from './client';

export type SavingsGoalStatus = 'ACTIVE' | 'COMPLETED' | 'PAUSED';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline?: string | null;
  notes?: string | null;
  status: SavingsGoalStatus;
  progress_pct: number;
  milestones_reached: number[];
  next_milestone_pct: number | null;
  created_at: string;
};

export type SavingsDeposit = {
  id: number;
  amount: number;
  note?: string | null;
  deposited_at: string;
  created_at: string;
};

export type SavingsGoalCreate = {
  name: string;
  target_amount: number;
  currency?: string;
  deadline?: string | null;
  notes?: string | null;
  initial_amount?: number;
};

export type SavingsGoalUpdate = Partial<Omit<SavingsGoalCreate, 'initial_amount'>> & {
  status?: SavingsGoalStatus;
};

export async function listGoals(status?: string): Promise<SavingsGoal[]> {
  const qs = status ? `?status=${status}` : '';
  return api<SavingsGoal[]>(`/savings${qs}`);
}

export async function createGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings', { method: 'POST', body: payload });
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`);
}

export async function updateGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api(`/savings/${id}`, { method: 'DELETE' });
}

export async function addDeposit(
  goalId: number,
  payload: { amount: number; note?: string; deposited_at?: string },
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${goalId}/deposits`, { method: 'POST', body: payload });
}

export async function listDeposits(goalId: number): Promise<SavingsDeposit[]> {
  return api<SavingsDeposit[]>(`/savings/${goalId}/deposits`);
}
