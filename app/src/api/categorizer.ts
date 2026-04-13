import { api } from './client';
export async function suggestCategory(description: string): Promise<{ suggested_category: string | null; confidence: number; matched_keyword: string | null }> { return api('/categorize/suggest', { method: 'POST', body: { description } }); }
export async function bulkCategorize(): Promise<{ results: any[]; total: number; categorized: number }> { return api('/categorize/bulk', { method: 'POST' }); }
export async function getKeywords(): Promise<{ categories: Record<string, string[]> }> { return api('/categorize/keywords'); }
