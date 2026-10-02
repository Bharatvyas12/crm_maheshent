'use client';

import { api, apiFetch } from '@/lib/api-client';
import type {
  AttendanceCorrection,
  AttendanceEvent,
  AttendanceRecord,
  AttendanceVerification,
  BreakSession,
  BreakType,
  Holiday,
  Paginated,
  QrToken,
  VerificationResult
} from '@/lib/types';

/** Evidence payload shared by check-in and check-out (docs/03_API_CONTRACT.md section 4.2). */
export interface AttendanceEvidence {
  latitude?: number | null;
  longitude?: number | null;
  accuracy_meters?: number | null;
  location_captured_at?: string | null;
  qr_token?: string | null;
  client_time?: string;
  device_info?: string;
}

export interface AttendanceRecordWithVerification extends AttendanceRecord {
  verification?: VerificationResult | null;
}

export function getToday(): Promise<AttendanceRecord> {
  return api.get<AttendanceRecord>('/attendance/me/today');
}

export function checkIn(evidence: AttendanceEvidence, idempotencyKey: string): Promise<AttendanceRecordWithVerification> {
  return apiFetch<AttendanceRecordWithVerification>('/attendance/check-in', {
    method: 'POST',
    body: evidence,
    idempotencyKey
  });
}

export function checkOut(evidence: AttendanceEvidence, idempotencyKey: string): Promise<AttendanceRecordWithVerification> {
  return apiFetch<AttendanceRecordWithVerification>('/attendance/check-out', {
    method: 'POST',
    body: evidence,
    idempotencyKey
  });
}

export function startBreak(breakTypeId: string, idempotencyKey: string): Promise<BreakSession> {
  return apiFetch<BreakSession>('/attendance/break/start', {
    method: 'POST',
    body: { break_type_id: breakTypeId },
    idempotencyKey
  });
}

export function endBreak(idempotencyKey: string): Promise<BreakSession> {
  return apiFetch<BreakSession>('/attendance/break/end', { method: 'POST', body: {}, idempotencyKey });
}

export function listMyAttendance(params: { from?: string; to?: string; page?: number; page_size?: number } = {}) {
  return api.get<Paginated<AttendanceRecord>>('/attendance/me', params);
}

export interface AttendanceSummary {
  present_days: number;
  half_days: number;
  partial_days: number;
  absent_days: number;
  leave_days: number;
  worked_seconds: number;
  break_seconds: number;
  overtime_seconds: number;
  late_minutes: number;
}

export function mySummary(params: { from?: string; to?: string } = {}) {
  return api.get<AttendanceSummary>('/attendance/me/summary', params);
}

export function listAttendance(params: {
  employee_id?: string;
  department?: string;
  status?: string;
  day_classification?: string;
  from?: string;
  to?: string;
  q?: string;
  sort?: string;
  page?: number;
  page_size?: number;
} = {}) {
  return api.get<Paginated<AttendanceRecord>>('/attendance', params);
}

export function getAttendanceRecord(id: string) {
  return api.get<AttendanceRecord>(`/attendance/${id}`);
}

export function getAttendanceEvents(id: string) {
  return api.get<{ items: AttendanceEvent[] }>(`/attendance/${id}/events`);
}

export function getAttendanceVerifications(id: string) {
  return api.get<{ items: AttendanceVerification[] }>(`/attendance/${id}/verifications`);
}

export function recomputeAttendance(id: string, reason: string) {
  return api.post<AttendanceRecord>(`/attendance/${id}/recompute`, { reason });
}

export function listBreakTypes(includeInactive = false) {
  return api.get<{ items: BreakType[] }>('/break-types', { include_inactive: includeInactive || undefined });
}

export function createBreakType(body: Partial<BreakType> & { code: string; name: string }) {
  return api.post<BreakType>('/break-types', body);
}

export function updateBreakType(id: string, body: Partial<BreakType>) {
  return api.patch<BreakType>(`/break-types/${id}`, body);
}

export function listHolidays(year: number) {
  return api.get<{ items: Holiday[] }>('/holidays', { year });
}

export function createHoliday(body: { holiday_date: string; name: string; is_paid: boolean; is_working_day: boolean }) {
  return api.post<Holiday>('/holidays', body);
}

export function deleteHoliday(id: string) {
  return api.delete<void>(`/holidays/${id}`);
}

export function createQrToken(purpose?: string) {
  return api.post<QrToken>('/attendance/qr-tokens', purpose ? { purpose } : {});
}

export function getCurrentQrToken(purpose = 'ATTENDANCE') {
  return api.get<QrToken>('/attendance/qr-tokens/current', { purpose });
}

// --- Corrections -----------------------------------------------------------

export interface CorrectionInput {
  attendance_record_id: string;
  correction_type: string;
  requested_check_in_at?: string | null;
  requested_check_out_at?: string | null;
  requested_break_start_at?: string | null;
  requested_break_end_at?: string | null;
  reason: string;
  attachment_file_id?: string | null;
}

export function createCorrection(body: CorrectionInput) {
  return api.post<AttendanceCorrection>('/attendance/corrections', body);
}

export function listMyCorrections(params: { status?: string; page?: number } = {}) {
  return api.get<Paginated<AttendanceCorrection>>('/attendance/corrections/mine', params);
}

export function listCorrections(params: { employee_id?: string; status?: string; from?: string; to?: string; page?: number } = {}) {
  return api.get<Paginated<AttendanceCorrection>>('/attendance/corrections', params);
}

export function approveCorrection(id: string, body: { decision_notes?: string; adjust_to?: Record<string, unknown> }) {
  return api.post<AttendanceCorrection>(`/attendance/corrections/${id}/approve`, body);
}

export function rejectCorrection(id: string, decisionNotes: string) {
  return api.post<AttendanceCorrection>(`/attendance/corrections/${id}/reject`, { decision_notes: decisionNotes });
}

export function cancelCorrection(id: string, reason: string) {
  return api.post<AttendanceCorrection>(`/attendance/corrections/${id}/cancel`, { reason });
}