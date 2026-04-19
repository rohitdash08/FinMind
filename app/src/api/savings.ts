import { api } from './client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export type SavingsMilestone = {
  id: number;
  title: string;
  target_amount: number;
  is_completed: boolean;
  completed_at?: string;
};

export type SavingsGoal = {
  id: number;
  title: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline?: string;
  status: 'on-track' | 'ahead' | 'behind' | 'completed';
  created_at: string;
  milestones: SavingsMilestone[];
};

export const useSavingsGoals = () => {
  return useQuery({
    queryKey: ['savings-goals'],
    queryFn: () => api<SavingsGoal[]>('/savings/goals'),
  });
};

export const useCreateGoal = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<SavingsGoal>) => api<SavingsGoal>('/savings/goals', { method: 'POST', body: data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['savings-goals'] }),
  });
};

export const useUpdateGoal = (goalId: number) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<SavingsGoal>) => api<SavingsGoal>(`/savings/goals/${goalId}`, { method: 'PATCH', body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savings-goals'] });
      queryClient.invalidateQueries({ queryKey: ['savings-goals', goalId] });
    },
  });
};

export const useDeleteGoal = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalId: number) => api(`/savings/goals/${goalId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['savings-goals'] }),
  });
};

export const useAddMilestone = (goalId: number) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<SavingsMilestone>) => api<SavingsMilestone>(`/savings/goals/${goalId}/milestones`, { method: 'POST', body: data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['savings-goals'] }),
  });
};
