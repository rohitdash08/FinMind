import { api } from './client';

export type WeeklyDigest = {
  period: {
    start: string;
    end: string;
  };
  total_expenses: number;
  total_income: number;
  net: number;
  top_categories: Array<{ category_id: number | null; name: string; amount: number }>;
  daily_average: number;
  wow_change: number;
  narrative: string;
  transactions_count: number;
  method: 'gemini' | 'heuristic' | string;
};

export type DigestPreferences = {
  enabled: boolean;
  day_of_week: number;
  send_email: boolean;
};

export async function getWeeklyDigest(): Promise<WeeklyDigest> {
  return api<WeeklyDigest>('/digest/weekly');
}

export async function getDigestPreferences(): Promise<DigestPreferences> {
  return api<DigestPreferences>('/digest/preferences');
}

export async function updateDigestPreferences(
  prefs: Partial<DigestPreferences>,
): Promise<DigestPreferences> {
  return api<DigestPreferences>('/digest/preferences', {
    method: 'PUT',
    body: prefs,
  });
}
