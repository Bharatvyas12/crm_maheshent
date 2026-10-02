'use client';

import { api, apiFetch } from '@/lib/api-client';
import type { Leave, LeaveBalance, LeaveBalanceMovement, LeaveType, Paginated } from '@/lib/types';

export function listLeaveTypes(includeInactive = false) {
  return api.get<{ items: LeaveType[] }>('/leave-types', { include_inactive: includeInactive || undefined });
}

export function createLeaveType(body: Partial<LeaveType> & { code: string; name: string }) {
  return api.post<LeaveType>('/leave-types', body);
}

export function updateLeaveType(id: string, body: Partial<LeaveType>) {
  return api.patch<LeaveType>(`/leave-types/${id}`, body);
}

export interface LeaveApplicationInput {
  leave_type_id: string;
  start_date: string;
  end_date: string;
  is_half_day?: boolean;
  half_day_period?: string;
  reason: string;
  attachment_file_id?: string | null;
}

export function applyLeave(body: LeaveApplicationInput, idempotencyKey: string) {
  return apiFetch<Leave>('/leaves', { method: 'POST', body, idempotencyKey });
}

export function listMyLeaves(params: { status?: string; leave_type_id?: string; from?: string; to?: string; page?: number } = {}) {
  return api.get<Paginated<Leave>>('/leaves/mine', params);
}

export function listLeaves(params: { employee_id?: string; leave_type_id?: string; status?: string; from?: string; to?: string; sort?: string; page?: number } = {}) {
  return api.get<Paginated<Leave>>('/leaves', params);
}

export function getLeave(id: string) {
  return api.get<Leave>(`/leaves/${id}`);
}

export function approveLeave(id: string, decisionNotes?: string) {
  return api.post<Leave>(`/leaves/${id}/approve`, decisionNotes ? { decision_notes: decisionNotes } : {});
}

export function rejectLeave(id: string, decisionNotes: string) {
  return api.post<Leave>(`/leaves/${id}/reject`, { decision_notes: decisionNotes });
}

export function requestLeaveModification(id: string, decisionNotes: string) {
  return api.post<Leave>(`/leaves/${id}/request-modification`, { decision_notes: decisionNotes });
}

export function cancelLeave(id: string, reason: string) {
  return api.post<Leave>(`/leaves/${id}/cancel`, { reason });
}

export function myLeaveBalances(periodYear?: number) {
  return api.get<{ items: LeaveBalance[] }>('/leave-balances/mine', { period_year: periodYear });
}

export function listLeaveBalances(params: { employee_id?: string; leave_type_id?: string; period_year?: number; page?: number } = {}) {
  return api.get<Paginated<LeaveBalance>>('/leave-balances', params);
}

export function listBalanceMovements(id: string, params: { page?: number; page_size?: number } = {}) {
  return api.get<Paginated<LeaveBalanceMovement>>(`/leave-balances/${id}/movements`, params);
}

export function adjustLeaveBalance(body: { employee_id: string; leave_type_id: string; period_year: number; days: string; reason: string }) {
  return api.post<LeaveBalance>('/leave-balances/adjustments', body);
}