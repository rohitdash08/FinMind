import { api } from './client';
export type Notification = { id: number; message: string; priority: string; group: string; created_at: string };
export async function createNotification(message: string, priority?: string, group?: string): Promise<Notification> { return api('/notifications', { method: 'POST', body: { message, priority, group } }); }
export async function listNotifications(priority?: string): Promise<Notification[]> { return api('/notifications' + (priority ? '?priority=' + priority : '')); }
export async function getGrouped(): Promise<{ groups: Record<string, Notification[]>; group_count: number }> { return api('/notifications/grouped'); }
