import { api } from './client';

// ── Types ──────────────────────────────────────────────────────────────

export interface SavingsGoal {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  progress: number;
  currency: string;
  deadline: string | null;
  color: string;
  icon: string;
  completed: boolean;
  completed_at: string | null;
  created_at: string | null;
}

export interface SavingsContribution {
  id: number;
  goal_id: number;
  amount: number;
  notes: string | null;
  contributed_at: string | null;
  created_at: string | null;
}

export interface GoalsSummary {
  total_saved: number;
  total_target: number;
  goals_count: number;
  completed_count: number;
  active_count: number;
  nearest_deadline: {
    goal_id: number;
    name: string;
    deadline: string;
  } | null;
}

export interface ContributionResponse {
  contribution: SavingsContribution;
  goal: SavingsGoal;
  just_completed: boolean;
}

export type GoalCreate = {
  name: string;
  target_amount: number;
  currency?: string;
  deadline?: string | null;
  color?: string;
  icon?: string;
};

export type GoalUpdate = Partial<GoalCreate>;

// ── API calls ──────────────────────────────────────────────────────────

export async function listGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings/goals');
}

export async function createGoal(payload: GoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings/goals', { method: 'POST', body: payload });
}

export async function updateGoal(id: number, payload: GoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/goals/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings/goals/${id}`, { method: 'DELETE' });
}

export async function addContribution(
  goalId: number,
  payload: { amount: number; notes?: string; contributed_at?: string },
): Promise<ContributionResponse> {
  return api<ContributionResponse>(`/savings/goals/${goalId}/contribute`, {
    method: 'POST',
    body: payload,
  });
}

export async function listContributions(goalId: number): Promise<SavingsContribution[]> {
  return api<SavingsContribution[]>(`/savings/goals/${goalId}/contributions`);
}

export async function getGoalsSummary(): Promise<GoalsSummary> {
  return api<GoalsSummary>('/savings/goals/summary');
}
