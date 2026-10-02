'use client';

import { api, apiFetch } from '@/lib/api-client';
import type { CursorPage, ListResponse, NotificationItem, NotificationPreference } from '@/lib/types';

export function listNotifications(params: { is_read?: boolean; cursor?: string; limit?: number } = {}) {
  return api.get<CursorPage<NotificationItem>>('/notifications', {
    is_read: params.is_read,
    cursor: params.cursor,
    limit: params.limit ?? 30
  });
}

export function fetchUnreadCount() {
  return api.get<{ unread: number }>('/notifications/unread-count');
}

export function markNotificationRead(id: string) {
  return api.post<void>(`/notifications/${id}/read`);
}

export function markNotificationsRead(body: { ids?: string[]; all?: boolean }) {
  return api.post<{ updated: number }>('/notifications/read', body);
}

export function fetchNotificationPreferences() {
  return api.get<ListResponse<NotificationPreference>>('/notification-preferences');
}

export function updateNotificationPreferences(preferences: Array<{ event_type: string; channel: string; is_enabled: boolean }>) {
  return api.patch<ListResponse<NotificationPreference>>('/notification-preferences', { preferences });
}

export interface PushSubscriptionInput {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent?: string;
}

export function createPushSubscription(body: PushSubscriptionInput) {
  return apiFetch<{ id: string }>('/push-subscriptions', { method: 'POST', body });
}

export function deletePushSubscription(id: string) {
  return api.delete<void>(`/push-subscriptions/${id}`);
}

export interface BroadcastInput {
  title: string;
  body: string;
  audience: { scope: string; employee_ids?: string[] };
  priority?: string;
}

export function broadcastNotification(body: BroadcastInput) {
  return api.post<{ created: number }>('/notifications/broadcast', body);
}