'use client';

import { api } from '@/lib/api-client';
import type { ListResponse, Paginated, PermissionCatalogItem, Role } from '@/lib/types';

export function listRoles(params: { include_system?: boolean; page?: number } = {}) {
  return api.get<Paginated<Role>>('/roles', params);
}

export function createRole(body: { code: string; name: string; description?: string; permission_codes: string[] }) {
  return api.post<Role>('/roles', body);
}

export function getRole(id: string) {
  return api.get<Role>(`/roles/${id}`);
}

export function updateRole(id: string, body: { name?: string; description?: string; is_assignable?: boolean }) {
  return api.patch<Role>(`/roles/${id}`, body);
}

export function setRolePermissions(id: string, body: { permission_codes: string[]; reason: string }) {
  return api.put<Role>(`/roles/${id}/permissions`, body);
}

export function deleteRole(id: string) {
  return api.delete<void>(`/roles/${id}`);
}

export function listPermissions(module?: string) {
  return api.get<ListResponse<PermissionCatalogItem>>('/permissions', { module });
}