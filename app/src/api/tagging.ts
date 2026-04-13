import { api } from './client';

export type TaggingRule = {
  id: number;
  name: string;
  field: string;
  operator: string;
  value: string;
  category_id: number | null;
  tag: string | null;
  active: boolean;
  created_at: string;
};

export type ApplyResult = {
  matched: number;
  total_expenses: number;
  rules_applied: number;
};

export type TestMatch = {
  expense_id: number;
  expense_notes: string;
  expense_amount: number;
  matched_rule: string;
  would_assign_category: number | null;
  would_assign_tag: string | null;
};

export async function listRules(): Promise<TaggingRule[]> {
  return api<TaggingRule[]>('/tagging/rules');
}

export async function createRule(data: {
  name: string; field: string; operator: string; value: string;
  category_id?: number; tag?: string;
}): Promise<TaggingRule> {
  return api<TaggingRule>('/tagging/rules', { method: 'POST', body: data });
}

export async function deleteRule(id: number): Promise<void> {
  return api<void>('/tagging/rules/' + id, { method: 'DELETE' });
}

export async function applyRules(): Promise<ApplyResult> {
  return api<ApplyResult>('/tagging/rules/apply', { method: 'POST' });
}

export async function testRules(): Promise<{ matches: TestMatch[]; total_matches: number }> {
  return api('/tagging/rules/test', { method: 'POST' });
}
