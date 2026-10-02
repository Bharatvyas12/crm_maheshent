'use client';

import { api, apiFetch, type QueryValue } from '@/lib/api-client';
import type { DashboardSummary, ExportJob, ListResponse, Paginated, ReportCatalogItem } from '@/lib/types';

export interface ReportResult {
  items: Array<Record<string, unknown>>;
  totals?: Record<string, unknown> | null;
  page?: number;
  page_size?: number;
  total_items?: number;
  total_pages?: number;
  [key: string]: unknown;
}

/** GET /reports/dashboard-summary - numbers come from the server, never client aggregation. */
export function getDashboardSummary(asOf?: string): Promise<DashboardSummary> {
  return api.get<DashboardSummary>('/reports/dashboard-summary', { as_of: asOf });
}

export function getReportCatalog(): Promise<ListResponse<ReportCatalogItem>> {
  return api.get<ListResponse<ReportCatalogItem>>('/reports/catalog');
}

export type ReportType =
  | 'attendance'
  | 'work-hours'
  | 'breaks'
  | 'overtime'
  | 'tasks'
  | 'orders'
  | 'leaves'
  | 'advances'
  | 'ledger'
  | 'salary'
  | 'complaints';

export function runReport(reportType: ReportType, params: Record<string, QueryValue> = {}): Promise<ReportResult> {
  return api.get<ReportResult>(`/reports/${reportType}`, params);
}

export function createExport(body: { report_type: string; format: string; parameters: Record<string, unknown> }, idempotencyKey: string) {
  return apiFetch<ExportJob>('/reports/exports', { method: 'POST', body, idempotencyKey });
}

export function listExports(params: { mine?: boolean; status?: string; page?: number } = {}) {
  return api.get<Paginated<ExportJob>>('/reports/exports', params);
}

export function getExportJob(id: string) {
  return api.get<ExportJob>(`/reports/exports/${id}`);
}

export function deleteExportJob(id: string) {
  return api.delete<void>(`/reports/exports/${id}`);
}

export function createAuditExport(body: { format: string; filters: Record<string, unknown> }) {
  return apiFetch<ExportJob>('/audit-logs/exports', { method: 'POST', body });
}