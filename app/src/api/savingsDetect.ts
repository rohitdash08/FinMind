import { api } from './client';
export type Opportunity = { type: string; suggestion: string; amount?: number; potential_savings?: number };
export type DetectResult = { opportunities: Opportunity[]; total_potential_savings: number; opportunity_count: number };
export async function detectSavings(): Promise<DetectResult> { return api('/savings-opportunities'); }
