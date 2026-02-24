import { api } from './client';

export type ConditionType = 'keyword_match' | 'merchant_match' | 'amount_range';

export type RuleCondition = {
  type: ConditionType;
  value?: string;
  min?: number;
  max?: number;
};

export type AutoTagRule = {
  id: number;
  name: string;
  conditions: RuleCondition[];
  target_category_id: number;
  priority: number;
  active: boolean;
};

export type AutoTagRuleCreate = {
  name: string;
  conditions: RuleCondition[];
  target_category_id: number;
  priority?: number;
  active?: boolean;
};

export type AutoTagRuleUpdate = Partial<AutoTagRuleCreate>;

export async function listRules(): Promise<AutoTagRule[]> {
  return api<AutoTagRule[]>('/rules');
}

export async function createRule(payload: AutoTagRuleCreate): Promise<AutoTagRule> {
  return api<AutoTagRule>('/rules', { method: 'POST', body: payload });
}

export async function updateRule(id: number, payload: AutoTagRuleUpdate): Promise<AutoTagRule> {
  return api<AutoTagRule>(`/rules/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteRule(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/rules/${id}`, { method: 'DELETE' });
}
