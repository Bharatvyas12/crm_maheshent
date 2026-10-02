'use client';

import { useQuery } from '@tanstack/react-query';
import { getAuditLog, listAuditLogs } from './api';

export const useAuditLogs = (params: Parameters<typeof listAuditLogs>[0] = {}) =>
  useQuery({ queryKey: ['audit', 'list', params], queryFn: () => listAuditLogs(params) });

export const useAuditLog = (id: string) =>
  useQuery({ queryKey: ['audit', 'detail', id], queryFn: () => getAuditLog(id), enabled: Boolean(id) });