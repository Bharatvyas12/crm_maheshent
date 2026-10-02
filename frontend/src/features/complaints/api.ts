'use client';

import { api, apiFetch } from '@/lib/api-client';
import type { Complaint, ComplaintCategory, ComplaintComment, ListResponse, Paginated } from '@/lib/types';

export function listComplaintCategories(includeInactive = false) {
  return api.get<ListResponse<ComplaintCategory>>('/complaint-categories', { include_inactive: includeInactive || undefined });
}

export function createComplaintCategory(body: { code: string; name: string; default_priority?: string; default_visibility?: string }) {
  return api.post<ComplaintCategory>('/complaint-categories', body);
}

export interface ComplaintCreateInput {
  category_id: string;
  title: string;
  description: string;
  priority?: string;
  subject_employee_id?: string;
  attachment_file_ids?: string[];
}

export function createComplaint(body: ComplaintCreateInput) {
  return api.post<Complaint>('/complaints', body);
}

export function listMyComplaints(params: { status?: string; page?: number } = {}) {
  return api.get<Paginated<Complaint>>('/complaints/mine', params);
}

export function listComplaints(
  params: {
    status?: string;
    priority?: string;
    category_id?: string;
    raised_by?: string;
    subject_employee_id?: string;
    assigned_to?: string;
    from?: string;
    to?: string;
    q?: string;
    sort?: string;
    page?: number;
  } = {}
) {
  return api.get<Paginated<Complaint>>('/complaints', params);
}

export function getComplaint(id: string) {
  return api.get<Complaint>(`/complaints/${id}`);
}

export function updateComplaint(id: string, body: Partial<{ title: string; description: string; priority: string; category_id: string; visibility: string; assigned_to: string }>) {
  return api.patch<Complaint>(`/complaints/${id}`, body);
}

export function updateComplaintStatus(id: string, body: { to_status: string; reason?: string; internal_note?: string }) {
  return api.post<Complaint>(`/complaints/${id}/status`, body);
}

export function resolveComplaint(id: string, resolutionSummary: string) {
  return api.post<Complaint>(`/complaints/${id}/resolve`, { resolution_summary: resolutionSummary });
}

export function closeComplaint(id: string, note?: string) {
  return api.post<Complaint>(`/complaints/${id}/close`, note ? { note } : {});
}

export function rejectComplaint(id: string, rejectionReason: string) {
  return api.post<Complaint>(`/complaints/${id}/reject`, { rejection_reason: rejectionReason });
}

export function listComplaintComments(id: string, includeInternal = false) {
  return api.get<ListResponse<ComplaintComment>>(`/complaints/${id}/comments`, { include_internal: includeInternal || undefined });
}

export function addComplaintComment(id: string, body: { body: string; is_internal?: boolean }) {
  return api.post<ComplaintComment>(`/complaints/${id}/comments`, body);
}

export function addComplaintAttachment(id: string, body: { file_id: string; note?: string }) {
  return apiFetch<{ id: string }>(`/complaints/${id}/attachments`, { method: 'POST', body });
}