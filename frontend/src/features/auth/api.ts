'use client';

import { api, apiFetch } from '@/lib/api-client';
import type { Employee, ListResponse, SessionPayload, User } from '@/lib/types';

export interface LoginRequest {
  username: string;
  password: string;
}

export function login(body: LoginRequest): Promise<SessionPayload> {
  return apiFetch<SessionPayload>('/auth/login', { method: 'POST', body });
}

export function logout(): Promise<void> {
  return apiFetch<void>('/auth/logout', { method: 'POST' });
}

export function fetchSession(): Promise<SessionPayload> {
  return api.get<SessionPayload>('/auth/me');
}

export function changePassword(body: { current_password: string; new_password: string }): Promise<void> {
  return apiFetch<void>('/auth/change-password', { method: 'POST', body });
}

export interface MyProfile {
  user: User;
  employee: Employee | null;
}

export function fetchMyProfile(): Promise<MyProfile> {
  return api.get<MyProfile>('/me');
}

export type SelfServiceProfileFields = Pick<
  Employee,
  'phone' | 'email' | 'address_line' | 'emergency_contact_name' | 'emergency_contact_phone'
>;

export function updateMyProfile(body: Partial<SelfServiceProfileFields>): Promise<MyProfile> {
  return api.patch<MyProfile>('/me', body);
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_seen_at: string | null;
  ip: string | null;
  user_agent: string | null;
  is_current: boolean;
}

export function fetchMySessions(): Promise<ListResponse<SessionInfo>> {
  return api.get<ListResponse<SessionInfo>>('/auth/sessions');
}

export function revokeSession(sessionId: string): Promise<void> {
  return api.delete<void>(`/auth/sessions/${sessionId}`);
}