'use client';

import { api } from '@/lib/api-client';
import type { ListResponse, Paginated, SettingHistoryItem, SettingItem, SettingSchemaItem } from '@/lib/types';

export function fetchSettingsSchema() {
  return api.get<ListResponse<SettingSchemaItem>>('/settings/schema');
}

export function listSettings(params: { group?: string; keys?: string[] } = {}) {
  return api.get<ListResponse<SettingItem>>('/settings', { group: params.group, keys: params.keys });
}

export function getSetting(key: string) {
  return api.get<SettingItem>(`/settings/${key}`);
}

export function updateSettings(body: { reason: string; changes: Array<{ key: string; value: unknown }> }) {
  return api.patch<ListResponse<SettingItem>>('/settings', body);
}

export function settingHistory(key: string, params: { page?: number; page_size?: number } = {}) {
  return api.get<Paginated<SettingHistoryItem>>(`/settings/${key}/history`, params);
}