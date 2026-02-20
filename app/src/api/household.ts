import { api } from './client';

export interface Household {
  id: number;
  name: string;
  invite_code: string;
  created_by: number;
  created_at: string;
}

export interface HouseholdMember {
  user_id: number;
  email: string;
  role: string;
  joined_at: string;
}

export interface HouseholdExpense {
  id: number;
  user_id: number;
  amount: number;
  currency: string;
  category_id: number | null;
  expense_type: string;
  description: string;
  date: string;
  household_id: number;
}

export function getHousehold() {
  return api<Household>('/household');
}

export function createHousehold(name: string) {
  return api<Household>('/household', { method: 'POST', body: { name } });
}

export function getInviteCode() {
  return api<{ invite_code: string }>('/household/invite', { method: 'POST' });
}

export function joinHousehold(code: string) {
  return api<Household>(`/household/join/${code}`, { method: 'POST' });
}

export function getMembers() {
  return api<HouseholdMember[]>('/household/members');
}

export function getHouseholdExpenses() {
  return api<HouseholdExpense[]>('/household/expenses');
}
