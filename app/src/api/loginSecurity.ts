import { api } from './client';
export type LoginEvent = { id: number; ip_address: string; user_agent: string; success: boolean; suspicious: boolean; reason: string | null; created_at: string; };
export type LoginStats = { total_logins: number; failed_attempts: number; suspicious_events: number; unique_ips: number; };
export async function getLoginHistory(): Promise<LoginEvent[]> { return api('/login-security/history'); }
export async function getSuspiciousLogins(): Promise<LoginEvent[]> { return api('/login-security/suspicious'); }
export async function getLoginStats(): Promise<LoginStats> { return api('/login-security/stats'); }
