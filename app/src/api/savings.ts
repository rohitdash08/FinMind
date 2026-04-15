import { api } from "./client";

export interface SavingsMilestone {
  id: number;
  title: string;
  target_amount: number;
  reached: boolean;
  reached_at: string | null;
}

export interface SavingsGoal {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  status: "ACTIVE" | "COMPLETED" | "PAUSED";
  created_at: string;
  milestones?: SavingsMilestone[];
}

export const savings = {
  list: () => api<SavingsGoal[]>('/savings'),

  get: (goalId: number) => api<SavingsGoal>(`/savings/${goalId}`),

  create: (data: {
    name: string;
    target_amount: number;
    currency?: string;
    deadline?: string;
    current_amount?: number;
  }) => api<{ id: number }>('/savings', { method: 'POST', body: data }),

  update: (
    goalId: number,
    data: Partial<Omit<SavingsGoal, 'id' | 'created_at'>>
  ) => api<{ message: string }>(`/savings/${goalId}`, { method: 'PATCH', body: data }),

  contribute: (goalId: number, amount: number) =>
    api<{ message: string; current_amount: number; status: string }>(
      `/savings/${goalId}/contribute`,
      { method: 'POST', body: { amount } }
    ),

  delete: (goalId: number) => api<{ message: string }>(`/savings/${goalId}`, { method: 'DELETE' }),

  listMilestones: (goalId: number) => api<SavingsMilestone[]>(`/savings/${goalId}/milestones`),

  addMilestone: (
    goalId: number,
    data: { title: string; target_amount: number }
  ) => api<{ id: number }>(`/savings/${goalId}/milestones`, { method: 'POST', body: data }),

  updateMilestone: (
    goalId: number,
    milestoneId: number,
    data: Partial<Pick<SavingsMilestone, 'title' | 'target_amount'>>
  ) =>
    api<{ message: string }>(`/savings/${goalId}/milestones/${milestoneId}`, {
      method: 'PATCH',
      body: data,
    }),

  deleteMilestone: (goalId: number, milestoneId: number) =>
    api<{ message: string }>(`/savings/${goalId}/milestones/${milestoneId}`, {
      method: 'DELETE',
    }),
};
