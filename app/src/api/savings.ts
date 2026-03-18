import { api } from './client';

export type GoalStatus = 'ACTIVE' | 'PAUSED' | 'COMPLETED';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  status: GoalStatus;
  deadline: string | null;
  color: string;
  icon: string;
  progress_pct: number;
  milestones_reached: number[];
  estimated_completion: string | null;
  created_at: string;
  deposits?: SavingsDeposit[];
};

export type SavingsDeposit = {
  id: number;
  goal_id: number;
  amount: number;
  note: string | null;
  deposited_at: string;
};

export type SavingsSummary = {
  total_goals: number;
  active_goals: number;
  completed_goals: number;
  total_target: number;
  total_saved: number;
  total_remaining: number;
  overall_progress_pct: number;
  nearest_deadline: string | null;
};

export type GoalCreate = {
  name: string;
  target_amount: number;
  currency?: string;
  deadline?: string | null;
  color?: string;
  icon?: string;
};

export type GoalUpdate = Partial<GoalCreate> & { status?: GoalStatus };

export type DepositCreate = {
  amount: number;
  note?: string;
  deposited_at?: string;
};

export type DepositResponse = {
  deposit: SavingsDeposit;
  goal: SavingsGoal;
  milestones_newly_reached: number[];
};

export async function listGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings');
}

export async function createGoal(payload: GoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings', { method: 'POST', body: payload });
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`);
}

export async function updateGoal(id: number, payload: GoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings/${id}`, { method: 'DELETE' });
}

export async function addDeposit(goalId: number, payload: DepositCreate): Promise<DepositResponse> {
  return api<DepositResponse>(`/savings/${goalId}/deposits`, {
    method: 'POST',
    body: payload,
  });
}

export async function listDeposits(goalId: number): Promise<SavingsDeposit[]> {
  return api<SavingsDeposit[]>(`/savings/${goalId}/deposits`);
}

export async function getSummary(): Promise<SavingsSummary> {
  return api<SavingsSummary>('/savings/summary');
}
