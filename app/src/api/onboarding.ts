import { api } from './client';

export type FinancialGoal =
  | 'save_for_emergency'
  | 'pay_off_debt'
  | 'build_investments'
  | 'track_spending'
  | 'save_for_goal'
  | 'retirement';

export type LifestyleProfile =
  | 'student'
  | 'early_career'
  | 'family'
  | 'freelancer'
  | 'retired';

export type SpendingCategory = {
  name: string;
  enabled: boolean;
  monthly_budget?: number;
};

export type NotificationChannel = 'email' | 'whatsapp' | 'none';

export interface OnboardingProfile {
  financial_goals: FinancialGoal[];
  lifestyle: LifestyleProfile;
  monthly_income?: number;
  monthly_expense_estimate?: number;
  preferred_currency: string;
  spending_categories: SpendingCategory[];
  notification_channel: NotificationChannel;
  bill_reminder_days: number;
}

export interface OnboardingCompleteResponse {
  message: string;
  onboarding_complete: boolean;
}

export const ONBOARDING_STORAGE_KEY = 'fm_onboarding_draft';
export const ONBOARDING_COMPLETE_KEY = 'fm_onboarding_complete';

export function loadOnboardingDraft(): Partial<OnboardingProfile> | null {
  try {
    const raw = localStorage.getItem(ONBOARDING_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Partial<OnboardingProfile>) : null;
  } catch {
    return null;
  }
}

export function saveOnboardingDraft(data: Partial<OnboardingProfile>): void {
  localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(data));
}

export function clearOnboardingDraft(): void {
  localStorage.removeItem(ONBOARDING_STORAGE_KEY);
}

export function isOnboardingComplete(): boolean {
  return localStorage.getItem(ONBOARDING_COMPLETE_KEY) === 'true';
}

export function markOnboardingComplete(): void {
  localStorage.setItem(ONBOARDING_COMPLETE_KEY, 'true');
  clearOnboardingDraft();
  window.dispatchEvent(new Event('onboarding_complete'));
}

export async function completeOnboarding(
  profile: OnboardingProfile,
): Promise<OnboardingCompleteResponse> {
  return api<OnboardingCompleteResponse>('/onboarding/complete', {
    method: 'POST',
    body: profile,
  });
}

export const DEFAULT_SPENDING_CATEGORIES: SpendingCategory[] = [
  { name: 'Housing', enabled: true, monthly_budget: undefined },
  { name: 'Food & Groceries', enabled: true, monthly_budget: undefined },
  { name: 'Transport', enabled: true, monthly_budget: undefined },
  { name: 'Healthcare', enabled: false, monthly_budget: undefined },
  { name: 'Entertainment', enabled: false, monthly_budget: undefined },
  { name: 'Clothing', enabled: false, monthly_budget: undefined },
  { name: 'Education', enabled: false, monthly_budget: undefined },
  { name: 'Savings', enabled: true, monthly_budget: undefined },
  { name: 'Utilities', enabled: true, monthly_budget: undefined },
  { name: 'Personal Care', enabled: false, monthly_budget: undefined },
];
