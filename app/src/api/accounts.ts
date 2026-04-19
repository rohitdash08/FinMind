import { api } from './client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export type AccountType = 'BANK' | 'CASH' | 'CREDIT_CARD' | 'INVESTMENT';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  balance: number;
  currency: string;
  created_at: string;
};

export const useAccounts = () => {
  return useQuery({
    queryKey: ['accounts'],
    queryFn: () => api<FinancialAccount[]>('/accounts/'),
  });
};

export const useCreateAccount = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<FinancialAccount>) => api<FinancialAccount>('/accounts/', { method: 'POST', body: data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  });
};

export const useUpdateAccount = (accountId: number) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<FinancialAccount>) => api<FinancialAccount>(`/accounts/${accountId}`, { method: 'PATCH', body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
  });
};

export const useDeleteAccount = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (accountId: number) => api(`/accounts/${accountId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  });
};
