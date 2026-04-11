import { api } from './client';

export type RuleCondition = {
  field: 'description' | 'amount' | 'expense_type';
  operator: 'contains' | 'not_contains' | 'regex' | 'equals' | 'gt' | 'lt' | 'between';
  value: string | number | [number, number];
};

export type RuleActions = {
  set_category_id?: number | null;
  add_tags?: string[];
  set_expense_type?: 'EXPENSE' | 'INCOME' | null;
};

export type AutoTagRule = {
  id: number;
  name: string;
  priority: number;
  conditions: RuleCondition[];
  actions: RuleActions;
  active: boolean;
  created_at: string;
};

export type RuleCreate = {
  name: string;
  priority?: number;
  conditions: RuleCondition[];
  actions: RuleActions;
  active?: boolean;
};

export type RuleUpdate = Partial<RuleCreate>;

export type DryRunResult = {
  matched_rule_ids: number[];
  changes: {
    set_category_id: number | null;
    add_tags: string[];
    set_expense_type: string | null;
  };
};

export type ApplyAllResult = {
  updated: number;
  skipped: number;
};

export async function listRules(): Promise<AutoTagRule[]> {
  return api<AutoTagRule[]>('/rules');
}

export async function getRule(id: number): Promise<AutoTagRule> {
  return api<AutoTagRule>(`/rules/${id}`);
}

export async function createRule(payload: RuleCreate): Promise<AutoTagRule> {
  return api<AutoTagRule>('/rules', { method: 'POST', body: payload });
}

export async function updateRule(id: number, payload: RuleUpdate): Promise<AutoTagRule> {
  return api<AutoTagRule>(`/rules/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteRule(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/rules/${id}`, { method: 'DELETE' });
}

export async function testRule(transaction: {
  description?: string;
  amount?: number;
  expense_type?: string;
}): Promise<DryRunResult> {
  return api<DryRunResult>('/rules/test', { method: 'POST', body: { transaction } });
}

export async function applyAllRules(force?: boolean): Promise<ApplyAllResult> {
  return api<ApplyAllResult>('/rules/apply-all', { method: 'POST', body: { force: !!force } });
}
