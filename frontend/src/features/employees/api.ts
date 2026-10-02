'use client';

import { api } from '@/lib/api-client';
import type { Employee, ListResponse, Paginated, User } from '@/lib/types';

export function listEmployees(params: { status?: string; department?: string; employment_type?: string; q?: string; sort?: string; page?: number; page_size?: number } = {}) {
  return api.get<Paginated<Employee>>('/employees', params);
}

export interface CreateEmployeeInput {
  employee_code: string;
  full_name: string;
  phone?: string;
  email?: string;
  date_of_joining: string;
  employment_type: string;
  department?: string;
  designation?: string;
  manager_employee_id?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  address_line?: string;
  username: string;
  initial_password?: string;
  roles?: string[];
  compensation?: { compensation_type: string; rate: string; currency: string; effective_from: string; reason: string };
}

export function createEmployee(body: CreateEmployeeInput) {
  return api.post<{ employee: Employee; user: User; initial_password?: string }>('/employees', body);
}

export function getEmployee(id: string) {
  return api.get<Employee>(`/employees/${id}`);
}

export function updateEmployee(id: string, body: Partial<CreateEmployeeInput>) {
  return api.patch<Employee>(`/employees/${id}`, body);
}

export function updateEmployeeSensitive(
  id: string,
  body: { bank_account_name?: string; bank_account_number?: string; bank_ifsc?: string; reason: string }
) {
  return api.patch<{ bank_account_name: string | null; bank_account_number_masked: string | null; bank_ifsc: string | null }>(
    `/employees/${id}/sensitive`,
    body
  );
}

export function deactivateEmployee(id: string, body: { date_of_exit: string; reason: string; revoke_sessions?: boolean; force?: boolean }) {
  return api.post<Employee>(`/employees/${id}/deactivate`, body);
}

export function reactivateEmployee(id: string, reason: string) {
  return api.post<Employee>(`/employees/${id}/reactivate`, { reason });
}

export interface CompensationRow {
  id: string;
  compensation_type: string;
  rate: string;
  currency: string;
  effective_from: string;
  effective_to: string | null;
  reason: string | null;
}

export function listCompensation(id: string) {
  return api.get<ListResponse<CompensationRow>>(`/employees/${id}/compensation`);
}

export function createCompensation(
  id: string,
  body: { compensation_type: string; rate: string; currency: string; effective_from: string; effective_to?: string | null; reason: string }
) {
  return api.post<CompensationRow>(`/employees/${id}/compensation`, body);
}

export function setUserRoles(id: string, body: { role_codes: string[]; reason: string }) {
  return api.put<{ roles: string[] }>(`/users/${id}/roles`, body);
}

export function listUsers(params: { status?: string; q?: string; page?: number } = {}) {
  return api.get<Paginated<User>>('/users', params);
}

export function resetUserPassword(body: { user_id: string; reason: string }) {
  return api.post<{ user_id: string; reset_token: string; expires_at: string }>('/auth/reset-password', body);
}