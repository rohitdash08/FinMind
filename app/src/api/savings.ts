import { api } from './client';

// --- Types ---

export type GoalMilestone = {
  id: number;
  name: string;
  target_percentage: number;
  reached_at: string | null;
};

export type GoalContribution = {
  id: number;
  amount: number;
  note: string | null;
  contributed_at: string | null;
};

export type SavingsGoal = {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  target_amount: number;
  current_amount: number;
  progress: number;
  currency: string;
  deadline: string | null;
  icon: string | null;
  color: string | null;
  is_completed: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type SavingsGoalDetail = SavingsGoal & {
  milestones: GoalMilestone[];
  contributions: GoalContribution[];
};

export type SavingsGoalCreate = {
  name: string;
  description?: string;
  target_amount: number;
  currency?: string;
  deadline?: string;
  icon?: string;
  color?: string;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate>;

export type ContributionCreate = {
  amount: number;
  note?: string;
};

export type SavingsSummary = {
  total_goals: number;
  completed_goals: number;
  in_progress_goals: number;
  total_target: number;
  total_saved: number;
  overall_progress: number;
};

// --- API Functions ---

export async function listGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings/goals');
}

export async function getGoal(id: number): Promise<SavingsGoalDetail> {
  return api<SavingsGoalDetail>(`/savings/goals/${id}`);
}

export async function createGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings/goals', { method: 'POST', body: payload });
}

export async function updateGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/goals/${id}`, { method: 'PUT', body: payload });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings/goals/${id}`, { method: 'DELETE' });
}

export async function addContribution(goalId: number, payload: ContributionCreate): Promise<SavingsGoalDetail> {
  return api<SavingsGoalDetail>(`/savings/goals/${goalId}/contribute`, { method: 'POST', body: payload });
}

export async function getSavingsSummary(): Promise<SavingsSummary> {
  return api<SavingsSummary>('/savings/summary');
}
