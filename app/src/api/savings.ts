import axios from "axios";

const BASE = "/savings";

export type GoalStatus = "active" | "completed" | "cancelled";

export interface Milestone {
  id: number;
  goal_id: number;
  name: string;
  target_amount: string;
  reached_at: string | null;
  created_at: string;
}

export interface SavingsGoal {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  target_amount: string;
  current_amount: string;
  currency: string;
  status: GoalStatus;
  deadline: string | null;
  created_at: string;
  updated_at: string;
  milestones: Milestone[];
}

export interface CreateGoalPayload {
  name: string;
  target_amount: string;
  description?: string;
  currency?: string;
  deadline?: string;
}

export interface UpdateGoalPayload {
  name?: string;
  description?: string;
  target_amount?: string;
  current_amount?: string;
  currency?: string;
  status?: GoalStatus;
  deadline?: string;
}

export interface CreateMilestonePayload {
  name: string;
  target_amount: string;
}

export interface UpdateMilestonePayload {
  name?: string;
  target_amount?: string;
  reached_at?: string;
}

// Goals

export const createGoal = (userId: number, payload: CreateGoalPayload) =>
  axios
    .post<SavingsGoal>(`${BASE}/goals`, payload, { params: { user_id: userId } })
    .then((r) => r.data);

export const listGoals = (userId: number) =>
  axios
    .get<SavingsGoal[]>(`${BASE}/goals`, { params: { user_id: userId } })
    .then((r) => r.data);

export const getGoal = (userId: number, goalId: number) =>
  axios
    .get<SavingsGoal>(`${BASE}/goals/${goalId}`, { params: { user_id: userId } })
    .then((r) => r.data);

export const updateGoal = (
  userId: number,
  goalId: number,
  payload: UpdateGoalPayload
) =>
  axios
    .patch<SavingsGoal>(`${BASE}/goals/${goalId}`, payload, {
      params: { user_id: userId },
    })
    .then((r) => r.data);

export const deleteGoal = (userId: number, goalId: number) =>
  axios
    .delete(`${BASE}/goals/${goalId}`, { params: { user_id: userId } })
    .then((r) => r.data);

// Milestones

export const createMilestone = (
  userId: number,
  goalId: number,
  payload: CreateMilestonePayload
) =>
  axios
    .post<Milestone>(`${BASE}/goals/${goalId}/milestones`, payload, {
      params: { user_id: userId },
    })
    .then((r) => r.data);

export const listMilestones = (userId: number, goalId: number) =>
  axios
    .get<Milestone[]>(`${BASE}/goals/${goalId}/milestones`, {
      params: { user_id: userId },
    })
    .then((r) => r.data);

export const updateMilestone = (
  userId: number,
  goalId: number,
  milestoneId: number,
  payload: UpdateMilestonePayload
) =>
  axios
    .patch<Milestone>(
      `${BASE}/goals/${goalId}/milestones/${milestoneId}`,
      payload,
      { params: { user_id: userId } }
    )
    .then((r) => r.data);

export const deleteMilestone = (
  userId: number,
  goalId: number,
  milestoneId: number
) =>
  axios
    .delete(`${BASE}/goals/${goalId}/milestones/${milestoneId}`, {
      params: { user_id: userId },
    })
    .then((r) => r.data);
