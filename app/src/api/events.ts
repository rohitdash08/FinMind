import { api } from './client';
export type Event = { id: number; event_type: string; created_at: string };
export async function emitEvent(eventType: string): Promise<Event> { return api('/events/emit', { method: 'POST', body: { event_type: eventType } }); }
export async function getEvents(limit?: number, type?: string): Promise<Event[]> { const q = new URLSearchParams(); if (limit) q.set('limit', String(limit)); if (type) q.set('type', type); return api('/events/stream?' + q); }
export async function getEventTypes(): Promise<{ types: string[] }> { return api('/events/types'); }
