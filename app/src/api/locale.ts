import { api } from './client';
export async function getSupportedLocales(): Promise<{ locales: string[] }> { return api('/locale/supported'); }
export async function getLocaleConfig(locale: string): Promise<any> { return api('/locale/config?locale=' + locale); }
export async function formatValue(value: number, type: string, locale: string): Promise<{ formatted: string }> { return api('/locale/format', { method: 'POST', body: { value, type, locale } }); }
