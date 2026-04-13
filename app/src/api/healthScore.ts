import { api } from './client';
export type HealthScore = { score: number; grade: string; factors: { name: string; score: number; max: number; detail: string }[]; tips: string[]; income: number; expenses: number };
export async function getHealthScore(): Promise<HealthScore> { return api('/health-score'); }
