import { api } from './client';

export type GoalCategory =
  | 'EMERGENCY'
  | 'VACATION'
  | 'HOME'
  | 'CAR'
  | 'EDUCATION'
  | 'RETIREMENT'
  | 'WEDDING'
  | 'GADGET'
  | 'INVESTMENT'
  | 'OTHER';

export type GoalStatus = 'ACTIVE' | 'COMPLETED' | 'CANCELLED';

export type Milestone = {
  id: number;
  title: string;
  target_percentage: number;
  reached: boolean;
  reached_at: string | null;
};

export type Contribution = {
  id: number;
  amount: number;
  contribution_type: 'DEPOSIT' | 'WITHDRAWAL';
  notes: string | null;
  created_at: string;
};

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  category: GoalCategory;
  status: GoalStatus;
  deadline: string | null;
  notes: string | null;
  progress_percentage: number;
  created_at: string;
  updated_at: string;
  milestones?: Milestone[];
  contributions?: Contribution[];
  newly_reached_milestones?: string[];
};

export type GoalCreate = {
  name: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  category?: GoalCategory;
  deadline?: string;
  notes?: string;
  milestones?: { title: string; target_percentage: number }[];
};

export type GoalUpdate = Partial<GoalCreate> & { status?: GoalStatus };

export type GoalsSummary = {
  active_goals: number;
  total_target: number;
  total_saved: number;
  overall_progress: number;
};

export type ContributionResponse = {
  message: string;
  current_amount: number;
  progress_percentage: number;
  newly_reached_milestones: {
    id: number;
    title: string;
    target_percentage: number;
  }[];
  status: GoalStatus;
};

export async function listGoals(
  status?: string,
): Promise<SavingsGoal[]> {
  const qs = new URLSearchParams();
  if (status) qs.set('status', status);
  const path = '/savings-goals' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<SavingsGoal[]>(path);
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`);
}

export async function createGoal(payload: GoalCreate): Promise<{ id: number }> {
  return api<{ id: number }>('/savings-goals', { method: 'POST', body: payload });
}

export async function updateGoal(
  id: number,
  payload: GoalUpdate,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`, {
    method: 'PATCH',
    body: payload,
  });
}

export async function deleteGoal(
  id: number,
): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings-goals/${id}`, { method: 'DELETE' });
}

export async function addContribution(
  goalId: number,
  payload: { amount: number; type?: 'DEPOSIT' | 'WITHDRAWAL'; notes?: string },
): Promise<ContributionResponse> {
  return api<ContributionResponse>(`/savings-goals/${goalId}/contribute`, {
    method: 'POST',
    body: payload,
  });
}

export async function listContributions(
  goalId: number,
): Promise<Contribution[]> {
  return api<Contribution[]>(`/savings-goals/${goalId}/contributions`);
}

export async function getGoalsSummary(): Promise<GoalsSummary> {
  return api<GoalsSummary>('/savings-goals/summary');
}
