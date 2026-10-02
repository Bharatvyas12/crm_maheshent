'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Order } from '@/lib/types';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import { useIdempotency } from '@/lib/idempotency';
import {
  addOrderAttachment,
  broadcastOrder,
  cancelOrder,
  claimOrder,
  createOrder,
  failOrder,
  getOrder,
  getOrderHistory,
  listAvailableOrders,
  listMyOrders,
  listOrderAttachments,
  listOrders,
  reassignOrder,
  releaseOrder,
  updateOrder,
  updateOrderStatus,
  type OrderAttachmentInput,
  type OrderCreateInput,
  type OrderStatusInput
} from './api';

const KEY = 'orders';

export function useOrderInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: [KEY] });
    void queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
  };
}

function useErrorToast() {
  const { push } = useToast();
  return (error: unknown, fallback: string) => {
    push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : fallback });
  };
}

export const useOrders = (params: Parameters<typeof listOrders>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'all', params], queryFn: () => listOrders(params) });

export const useAvailableOrders = (params: { page?: number; sort?: string } = {}) =>
  useQuery({ queryKey: [KEY, 'available', params], queryFn: () => listAvailableOrders(params) });

export const useMyOrders = (params: { status?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'mine', params], queryFn: () => listMyOrders(params) });

export const useOrder = (id: string) => useQuery({ queryKey: [KEY, 'order', id], queryFn: () => getOrder(id), enabled: Boolean(id) });

export const useOrderHistory = (id: string) =>
  useQuery({ queryKey: [KEY, 'history', id], queryFn: () => getOrderHistory(id), enabled: Boolean(id) });

export const useOrderAttachments = (id: string) =>
  useQuery({ queryKey: [KEY, 'attachments', id], queryFn: () => listOrderAttachments(id), enabled: Boolean(id) });

export function useCreateOrder() {
  const invalidate = useOrderInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: createOrder,
    onSuccess: (order) => {
      invalidate();
      push({ tone: 'success', title: `Order ${order.order_code} created (${order.status})` });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not create the order.' });
    }
  });
}

export function useUpdateOrder() {
  const invalidate = useOrderInvalidation();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<OrderCreateInput> }) => updateOrder(id, body),
    onSuccess: invalidate
  });
}

export function useBroadcastOrder() {
  const invalidate = useOrderInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body?: Parameters<typeof broadcastOrder>[1] }) => broadcastOrder(id, body ?? {}),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Order broadcast to the audience' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Broadcast failed.' });
    }
  });
}

/**
 * Claiming. On CLAIM_ALREADY_TAKEN the caller must show the conflict panel and refresh both the
 * order and the available list (docs/07_UI_SPEC.md section 5.4). The error is re-thrown so the
 * screen can branch on the code.
 */
export function useClaimOrder() {
  const invalidate = useOrderInvalidation();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: (id: string) => claimOrder(id, idem.key()),
    onSuccess: () => {
      idem.reset();
      invalidate();
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        if (error.code === 'CLAIM_ALREADY_TAKEN') {
          // Refresh order state so the UI reflects the winner.
          invalidate();
        }
        if (error.code === 'NETWORK_ERROR') {
          // Keep the key: the request may have succeeded server-side.
          return;
        }
        idem.reset();
      }
    }
  });
}

export function useReleaseOrder() {
  const invalidate = useOrderInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => releaseOrder(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Order released' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not release the order.' });
    }
  });
}

function useOrderAction<TArgs>(fn: (args: TArgs) => Promise<Order>, successMessage: string) {
  const invalidate = useOrderInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: successMessage });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Action failed.' });
    }
  });
}

export const useUpdateOrderStatus = () =>
  useOrderAction<{ id: string; body: OrderStatusInput }>(({ id, body }) => updateOrderStatus(id, body), 'Order status updated');

export const useReassignOrder = () =>
  useOrderAction<{ id: string; body: { reason: string; new_assignee_employee_id?: string } }>(
    ({ id, body }) => reassignOrder(id, body),
    'Order reassigned'
  );

export const useCancelOrder = () =>
  useOrderAction<{ id: string; body: { reason: string; cancellation_code?: string } }>(({ id, body }) => cancelOrder(id, body), 'Order cancelled');

export const useFailOrder = () =>
  useOrderAction<{ id: string; body: { failure_reason: string; reason_code?: string } }>(({ id, body }) => failOrder(id, body), 'Order marked failed');

export function useAddOrderAttachment() {
  const invalidate = useOrderInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: OrderAttachmentInput }) => addOrderAttachment(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Proof attached' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not attach the proof.' });
    }
  });
}