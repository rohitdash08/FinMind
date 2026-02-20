import { api } from './client';

export interface SavingsGoal {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  progress_pct: number;
  created_at: string;
}

export interface SavingsMilestone {
  id: number;
  goal_id: number;
  name: string;
  amount: number;
  reached_at: string | null;
}

export interface CreateGoalPayload {
  name: string;
  target_amount: number;
  currency?: string;
  deadline?: string;
  current_amount?: number;
}

export interface UpdateGoalPayload {
  name?: string;
  target_amount?: number;
  current_amount?: number;
  add_funds?: number;
  currency?: string;
  deadline?: string | null;
}

export function listGoals() {
  return api<SavingsGoal[]>('/savings/goals');
}

export function createGoal(payload: CreateGoalPayload) {
  return api<SavingsGoal>('/savings/goals', { method: 'POST', body: payload });
}

export function updateGoal(id: number, payload: UpdateGoalPayload) {
  return api<SavingsGoal>(`/savings/goals/${id}`, { method: 'PATCH', body: payload });
}

export function deleteGoal(id: number) {
  return api(`/savings/goals/${id}`, { method: 'DELETE' });
}

export function getMilestones(goalId: number) {
  return api<SavingsMilestone[]>(`/savings/goals/${goalId}/milestones`);
}
