'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import { useIdempotency } from '@/lib/idempotency';
import {
  createAuditExport,
  createExport,
  deleteExportJob,
  getDashboardSummary,
  getExportJob,
  getReportCatalog,
  listExports,
  runReport,
  type ReportType
} from './api';

export function useDashboardSummary(asOf?: string) {
  return useQuery({
    queryKey: ['dashboard-summary', asOf ?? 'now'],
    queryFn: () => getDashboardSummary(asOf),
    staleTime: 30_000
  });
}

export function useReportCatalog() {
  return useQuery({ queryKey: ['report-catalog'], queryFn: getReportCatalog, staleTime: 5 * 60_000 });
}

export function useReport(reportType: ReportType | null, params: Record<string, string | number | undefined>) {
  return useQuery({
    queryKey: ['report', reportType, params],
    queryFn: () => runReport(reportType as ReportType, params),
    enabled: Boolean(reportType)
  });
}

export function useExports(params: { status?: string; page?: number } = {}) {
  return useQuery({
    queryKey: ['exports', params],
    queryFn: () => listExports(params),
    refetchInterval: (query) => {
      const data = query.state.data;
      const pending = data?.items?.some((job) => job.status === 'QUEUED' || job.status === 'RUNNING');
      return pending ? 4000 : false;
    }
  });
}

export function useExportJob(id: string) {
  return useQuery({
    queryKey: ['export', id],
    queryFn: () => getExportJob(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'QUEUED' || status === 'RUNNING' ? 4000 : false;
    }
  });
}

export function useCreateExport() {
  const queryClient = useQueryClient();
  const { push } = useToast();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: (body: { report_type: string; format: string; parameters: Record<string, unknown> }) =>
      createExport(body, idem.key()),
    onSuccess: () => {
      idem.reset();
      void queryClient.invalidateQueries({ queryKey: ['exports'] });
      push({ tone: 'success', title: 'Export queued', description: 'It will appear in the exports list when ready.' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Export failed.' });
    }
  });
}

export function useCreateAuditExport() {
  const { push } = useToast();
  return useMutation({
    mutationFn: createAuditExport,
    onSuccess: () => push({ tone: 'success', title: 'Audit export queued' }),
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Export failed.' });
    }
  });
}

export function useDeleteExportJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteExportJob,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['exports'] })
  });
}