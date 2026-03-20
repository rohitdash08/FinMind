import { api } from './client';

export type NotificationPriority = 'critical' | 'high' | 'medium' | 'low';

export type NotificationItem = {
  id: number;
  type: string;
  priority: NotificationPriority;
  group: string;
  message: string;
  read: boolean;
  created_at: string;
};

export type NotificationsResponse = {
  notifications: Record<string, NotificationItem[]>;
  unread_count: number;
};

export async function listNotifications(): Promise<NotificationsResponse> {
  return api<NotificationsResponse>('/notifications');
}

export async function markNotificationRead(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/notifications/${id}/read`, { method: 'PATCH' });
}

export async function markAllNotificationsRead(): Promise<{ message: string; count: number }> {
  return api<{ message: string; count: number }>('/notifications/mark-all-read', {
    method: 'POST',
  });
}
