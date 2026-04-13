import { api } from './client';
export async function getCompressionStats(): Promise<any> { return api('/compression/stats'); }
export async function optimizePayload(payload: any): Promise<{ original_size: number; compressed_size: number; savings_pct: number }> { return api('/compression/optimize', { method: 'POST', body: { payload } }); }
export async function getCompressionConfig(): Promise<any> { return api('/compression/config'); }
