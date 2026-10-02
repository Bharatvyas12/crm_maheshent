'use client';

import { api } from '@/lib/api-client';
import type { AuditLog, CursorPage } from '@/lib/types';

export function listAuditLogs(
  params: {
    category?: string;
    action?: string;
    entity_type?: string;
    entity_id?: string;
    actor_user_id?: string;
    from?: string;
    to?: string;
    cursor?: string;
    limit?: number;
  } = {}
) {
  return api.get<CursorPage<AuditLog>>('/audit-logs', { ...params, limit: params.limit ?? 50 });
}

export function getAuditLog(id: string) {
  return api.get<AuditLog>(`/audit-logs/${id}`);
}