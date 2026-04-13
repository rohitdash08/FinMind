import { api } from './client';
export type IntegrityResult = { healthy: boolean; issues: { type: string; severity: string; count: number; message: string }[]; issue_count: number; summary: { total_records: number; total_income: number; total_expenses: number; balance: number } };
export async function checkIntegrity(): Promise<IntegrityResult> { return api('/reconciliation/check'); }
