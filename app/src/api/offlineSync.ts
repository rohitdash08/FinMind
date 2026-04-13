import { api } from './client';
export async function pushChanges(changes: any[]): Promise<{ applied: number; conflicts: any[] }> { return api('/sync/push', { method: 'POST', body: { changes } }); }
export async function pullChanges(since?: string): Promise<{ changes: any[] }> { return api('/sync/pull' + (since ? '?since=' + since : '')); }
export async function getSyncStatus(): Promise<{ pending: number; conflicts: number; total_synced: number }> { return api('/sync/status'); }
