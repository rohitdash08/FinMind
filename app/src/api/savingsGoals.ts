import { api } from './client';

export type SavingsGoalCategory =
  | 'EMERGENCY'
  | 'VACATION'
  | 'EDUCATION'
  | 'HOME'
  | 'CAR'
  | 'RETIREMENT'
  | 'INVESTMENT'
  | 'OTHER';

export type Milestone = {
  id: number;
  percentage: number;
  reached: boolean;
  reached_at: string | null;
};

export type Contribution = {
  id: number;
  amount: number;
  note: string | null;
  created_at: string;
};

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  category: SavingsGoalCategory;
  progress_pct: number;
  created_at: string;
  updated_at: string;
  milestones: Milestone[];
  contributions?: Contribution[];
  days_remaining: number | null;
  daily_target: number | null;
  monthly_target: number | null;
  on_track: boolean;
};

export type SavingsGoalCreate = {
  name: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string;
  category?: SavingsGoalCategory;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate>;

export type ContributeResponse = {
  goal: SavingsGoal;
  contribution: Contribution;
  newly_reached_milestones: Milestone[];
};

export async function listSavingsGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings-goals');
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

export async function contributeToGoal(
  id: number,
  amount: number,
  note?: string,
): Promise<ContributeResponse> {
  return api<ContributeResponse>(`/savings-goals/${id}/contribute`, {
    method: 'POST',
    body: { amount, note },
  });
}

export async function getGoalMilestones(id: number): Promise<Milestone[]> {
  return api<Milestone[]>(`/savings-goals/${id}/milestones`);
}

export const CATEGORY_LABELS: Record<SavingsGoalCategory, string> = {
  EMERGENCY: 'Emergency Fund',
  VACATION: 'Vacation',
  EDUCATION: 'Education',
  HOME: 'Home',
  CAR: 'Car',
  RETIREMENT: 'Retirement',
  INVESTMENT: 'Investment',
  OTHER: 'Other',
};

export const CATEGORY_COLORS: Record<SavingsGoalCategory, string> = {
  EMERGENCY: 'bg-red-500',
  VACATION: 'bg-blue-500',
  EDUCATION: 'bg-purple-500',
  HOME: 'bg-green-500',
  CAR: 'bg-orange-500',
  RETIREMENT: 'bg-indigo-500',
  INVESTMENT: 'bg-emerald-500',
  OTHER: 'bg-gray-500',
};
