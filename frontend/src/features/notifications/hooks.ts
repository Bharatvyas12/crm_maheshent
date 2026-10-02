'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/Toast';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import {
  broadcastNotification,
  createPushSubscription,
  deletePushSubscription,
  fetchNotificationPreferences,
  fetchUnreadCount,
  listNotifications,
  markNotificationRead,
  markNotificationsRead,
  updateNotificationPreferences
} from './api';

export function useUnreadCount() {
  return useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: fetchUnreadCount,
    refetchInterval: 60_000,
    select: (data) => data.unread
  });
}

export function useNotifications(params: { is_read?: boolean } = {}) {
  return useQuery({
    queryKey: ['notifications', 'list', params.is_read ?? 'all'],
    queryFn: () => listNotifications({ is_read: params.is_read })
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    }
  });
}

export function useMarkAllRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => markNotificationsRead({ all: true }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    }
  });
}

export function useNotificationPreferences() {
  return useQuery({ queryKey: ['notification-preferences'], queryFn: fetchNotificationPreferences });
}

export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();
  const { push } = useToast();
  return useMutation({
    mutationFn: updateNotificationPreferences,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notification-preferences'] });
      push({ tone: 'success', title: 'Preferences saved' });
    },
    onError: (error) => {
      const message = error instanceof ApiError ? describeProblem(error.problem).title : 'Could not save preferences.';
      push({ tone: 'error', title: message });
    }
  });
}

export function useCreatePushSubscription() {
  return useMutation({ mutationFn: createPushSubscription });
}

export function useDeletePushSubscription() {
  return useMutation({ mutationFn: deletePushSubscription });
}

export function useBroadcastNotification() {
  const { push } = useToast();
  return useMutation({
    mutationFn: broadcastNotification,
    onSuccess: (data) => push({ tone: 'success', title: `Broadcast sent to ${data.created} recipients` }),
    onError: (error) => {
      const message = error instanceof ApiError ? describeProblem(error.problem).title : 'Broadcast failed.';
      push({ tone: 'error', title: message });
    }
  });
}