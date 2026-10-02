'use client';

import { api, apiFetch } from '@/lib/api-client';
import type { ListResponse, Order, OrderAttachment, OrderClaim, OrderHistoryEntry, Paginated } from '@/lib/types';

export interface OrderCreateInput {
  order_code?: string;
  customer_name: string;
  customer_phone?: string;
  delivery_address?: string;
  delivery_notes?: string;
  item_summary?: string;
  item_count?: number | null;
  order_amount?: string;
  currency?: string;
  payment_mode?: string;
  notes?: string;
  proof_file_ids?: string[];
  broadcast?: { audience_scope: string; audience_payload?: Record<string, unknown> };
}

export function listOrders(params: { status?: string; assignee_employee_id?: string; unassigned?: boolean; from?: string; to?: string; q?: string; sort?: string; page?: number } = {}) {
  return api.get<Paginated<Order>>('/orders', params);
}

export function createOrder(body: OrderCreateInput) {
  return api.post<Order>('/orders', body);
}

export function getOrder(id: string) {
  return api.get<Order>(`/orders/${id}`);
}

export function updateOrder(id: string, body: Partial<OrderCreateInput>) {
  return api.patch<Order>(`/orders/${id}`, body);
}

export function broadcastOrder(id: string, body: { audience_scope?: string; audience_payload?: Record<string, unknown>; expires_at?: string } = {}) {
  return api.post<Order>(`/orders/${id}/broadcast`, body);
}

export function listAvailableOrders(params: { page?: number; page_size?: number; sort?: string } = {}) {
  return api.get<Paginated<Order>>('/orders/available', params);
}

/** The only way to obtain ownership. Atomic server-side (docs/03_API_CONTRACT.md section 9.2). */
export function claimOrder(id: string, idempotencyKey: string) {
  return apiFetch<{ order: Order; claim: OrderClaim }>(`/orders/${id}/claim`, { method: 'POST', body: {}, idempotencyKey });
}

export function releaseOrder(id: string, reason: string) {
  return api.post<Order>(`/orders/${id}/release`, { reason });
}

export function listMyOrders(params: { status?: string; include_history?: boolean; page?: number } = {}) {
  return api.get<Paginated<Order>>('/orders/mine', params);
}

export interface OrderStatusInput {
  to_status: string;
  reason?: string;
  note?: string;
  evidence?: { latitude?: number; longitude?: number; accuracy_meters?: number };
  proof_file_ids?: string[];
}

export function updateOrderStatus(id: string, body: OrderStatusInput) {
  return api.post<Order>(`/orders/${id}/status`, body);
}

export function reassignOrder(id: string, body: { reason: string; new_assignee_employee_id?: string }) {
  return api.post<Order>(`/orders/${id}/reassign`, body);
}

export function cancelOrder(id: string, body: { reason: string; cancellation_code?: string }) {
  return api.post<Order>(`/orders/${id}/cancel`, body);
}

export function failOrder(id: string, body: { failure_reason: string; reason_code?: string }) {
  return api.post<Order>(`/orders/${id}/fail`, body);
}

export interface OrderAttachmentInput {
  file_id: string;
  purpose: string;
  note?: string;
  latitude?: number;
  longitude?: number;
  accuracy_meters?: number;
  customer_confirmed?: boolean;
  customer_confirmation_method?: string;
}

export function addOrderAttachment(id: string, body: OrderAttachmentInput) {
  return api.post<OrderAttachment>(`/orders/${id}/attachments`, body);
}

export function getOrderHistory(id: string) {
  return api.get<ListResponse<OrderHistoryEntry>>(`/orders/${id}/history`);
}

export function listOrderAttachments(id: string) {
  return api.get<{ items: OrderAttachment[] }>(`/orders/${id}/attachments`);
}