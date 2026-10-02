'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import { useSession } from '@/features/auth/session';
import { fetchSettingsSchema, getSetting, listSettings, settingHistory, updateSettings } from './api';

const KEY = 'settings';

export function useSettingsSchema() {
  return useQuery({ queryKey: [KEY, 'schema'], queryFn: fetchSettingsSchema, staleTime: 5 * 60_000 });
}

export function useSettings(params: { group?: string } = {}) {
  return useQuery({ queryKey: [KEY, 'list', params], queryFn: () => listSettings(params) });
}

export function useSetting(key: string) {
  return useQuery({ queryKey: [KEY, 'setting', key], queryFn: () => getSetting(key), enabled: Boolean(key) });
}

export function useSettingHistory(key: string, enabled = true) {
  return useQuery({ queryKey: [KEY, 'history', key], queryFn: () => settingHistory(key), enabled: Boolean(key) && enabled });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  const { push } = useToast();
  return useMutation({
    mutationFn: updateSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: [KEY] });
      // Settings feed the session payload (timezone, currency, verification mode).
      await queryClient.invalidateQueries({ queryKey: ['session'] });
      push({ tone: 'success', title: 'Settings saved' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not save settings.' });
    }
  });
}

/** Business timezone for formatting, taken from the session settings the server provided. */
export function useBusinessTimezone(): string {
  const { settings } = useSession();
  return settings.business_timezone || 'UTC';
}

export function useCurrency(): string {
  const { settings } = useSession();
  return settings.currency || 'INR';
}