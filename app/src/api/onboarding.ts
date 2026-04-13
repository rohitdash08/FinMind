import { api } from './client';

export type OnboardingStatus = {
  has_expense: boolean;
  has_category: boolean;
  has_bill: boolean;
  has_budget_goal: boolean;
  profile_complete: boolean;
};

export type StepResult = {
  step: string;
  completed?: boolean;
  already_completed?: boolean;
};

export type Suggestion = {
  step: string;
  action: string;
};

export async function getStatus(): Promise<OnboardingStatus> {
  return api<OnboardingStatus>('/onboarding/status');
}

export async function completeStep(step: string): Promise<StepResult> {
  return api<StepResult>('/onboarding/complete-step', {
    method: 'POST',
    body: { step },
  });
}

export async function getSuggestions(): Promise<Suggestion[]> {
  return api<Suggestion[]>('/onboarding/suggestions');
}
