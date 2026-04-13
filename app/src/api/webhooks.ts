import { api } from './client';
export type WebhookSub = { id: number; url: string; events: string[]; active: boolean; created_at: string; };
export async function listWebhooks(): Promise<WebhookSub[]> { return api('/webhooks'); }
export async function createWebhook(data: { url: string; events: string[]; secret?: string }): Promise<WebhookSub> { return api('/webhooks', { method: 'POST', body: data }); }
export async function deleteWebhook(id: number): Promise<void> { return api('/webhooks/' + id, { method: 'DELETE' }); }
export async function listValidEvents(): Promise<{ events: string[] }> { return api('/webhooks/events'); }
export async function testWebhook(subscriptionId: number): Promise<{ delivered: boolean; status_code?: number; error?: string }> { return api('/webhooks/test', { method: 'POST', body: { subscription_id: subscriptionId } }); }
