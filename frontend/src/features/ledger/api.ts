'use client';

import { api, apiFetch } from '@/lib/api-client';
import type { Advance, LedgerEntry, LedgerSummary, Paginated, PayrollRun, SalaryRecord } from '@/lib/types';

/** Ledger reads return a paginated page plus a summary block (docs/03_API_CONTRACT.md section 11.1). */
export interface LedgerPage extends Paginated<LedgerEntry> {
  summary?: LedgerSummary | null;
}

export function myLedger(params: { from?: string; to?: string; entry_type?: string; page?: number } = {}) {
  return api.get<LedgerPage>('/ledger/me', params);
}

export function listLedger(params: { employee_id?: string; entry_type?: string; direction?: string; period_year?: number; period_month?: number; from?: string; to?: string; page?: number } = {}) {
  return api.get<LedgerPage>('/ledger', params);
}

export function getLedgerEntry(id: string) {
  return api.get<LedgerEntry>(`/ledger/${id}`);
}

export interface LedgerEntryInput {
  employee_id: string;
  entry_type: string;
  direction: string;
  amount: string;
  currency?: string;
  business_date: string;
  period_year?: number;
  period_month?: number;
  reason: string;
  reference_type?: string;
  reference_id?: string;
}

export function createLedgerEntry(body: LedgerEntryInput, idempotencyKey: string) {
  return apiFetch<LedgerEntry>('/ledger/entries', { method: 'POST', body, idempotencyKey });
}

export function reverseLedgerEntry(id: string, reason: string) {
  return api.post<LedgerEntry>(`/ledger/entries/${id}/reverse`, { reason });
}

export function ledgerBalance(employeeId: string, asOf?: string) {
  return api.get<LedgerSummary>(`/ledger/balance/${employeeId}`, { as_of: asOf });
}

// --- Advances --------------------------------------------------------------

export function myAdvances(params: { status?: string; page?: number } = {}) {
  return api.get<Paginated<Advance>>('/advances/mine', params);
}

export function listAdvances(params: { employee_id?: string; status?: string; from?: string; to?: string; page?: number } = {}) {
  return api.get<Paginated<Advance>>('/advances', params);
}

export function getAdvance(id: string) {
  return api.get<Advance>(`/advances/${id}`);
}

export interface AdvanceCreateInput {
  employee_id: string;
  amount: string;
  currency?: string;
  issued_on: string;
  reason: string;
  repayment_mode: string;
  installment_count?: number;
  installment_amount?: string;
}

export function createAdvance(body: AdvanceCreateInput, idempotencyKey: string) {
  return apiFetch<Advance>('/advances', { method: 'POST', body, idempotencyKey });
}

export function approveAdvance(id: string, decisionNotes?: string) {
  return api.post<Advance>(`/advances/${id}/approve`, decisionNotes ? { decision_notes: decisionNotes } : {});
}

export function rejectAdvance(id: string, decisionNotes: string) {
  return api.post<Advance>(`/advances/${id}/reject`, { decision_notes: decisionNotes });
}

export function addAdvanceRepayment(id: string, body: { amount: string; business_date: string; reason: string }, idempotencyKey: string) {
  return apiFetch<Advance>(`/advances/${id}/repayments`, { method: 'POST', body, idempotencyKey });
}

export function writeOffAdvance(id: string, body: { amount?: string; reason: string }) {
  return api.post<Advance>(`/advances/${id}/write-off`, body);
}

// --- Payroll ---------------------------------------------------------------

export function listPayrollRuns(params: { period_year?: number; status?: string; page?: number } = {}) {
  return api.get<Paginated<PayrollRun>>('/payroll/runs', params);
}

export function createPayrollRun(body: { period_year: number; period_month: number; notes?: string }) {
  return api.post<PayrollRun>('/payroll/runs', body);
}

export function getPayrollRun(id: string) {
  return api.get<PayrollRun>(`/payroll/runs/${id}`);
}

export function computePayrollRun(id: string, body: { employee_ids?: string[]; reason?: string } = {}) {
  return api.post<PayrollRun>(`/payroll/runs/${id}/compute`, body);
}

/** `force` requires salary.finalize plus ledger.entry.adjust and is recorded in the audit log. */
export function finalizePayrollRun(id: string, reason?: string, force?: boolean) {
  const body: Record<string, unknown> = {};
  if (reason) body.reason = reason;
  if (force) body.force = true;
  return api.post<PayrollRun>(`/payroll/runs/${id}/finalize`, body);
}

export function lockPayrollRun(id: string, reason: string) {
  return api.post<PayrollRun>(`/payroll/runs/${id}/lock`, { reason });
}

export function unlockPayrollRun(id: string, reason: string) {
  return api.post<PayrollRun>(`/payroll/runs/${id}/unlock`, { reason });
}

export function markPayrollRunPaid(id: string, body: { paid_on: string; reason?: string }, idempotencyKey: string) {
  return apiFetch<PayrollRun>(`/payroll/runs/${id}/mark-paid`, { method: 'POST', body, idempotencyKey });
}

export function listSalaryRecords(params: { payroll_run_id?: string; employee_id?: string; period_year?: number; period_month?: number; status?: string; page?: number } = {}) {
  return api.get<Paginated<SalaryRecord>>('/salary-records', params);
}

export function getSalaryRecord(id: string) {
  return api.get<SalaryRecord>(`/salary-records/${id}`);
}