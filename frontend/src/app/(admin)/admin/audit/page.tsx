'use client';

import { useState } from 'react';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { SelectiveFields } from '@/components/ui/SelectiveFields';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { SelectField, TextField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { useAuditLogs } from '@/features/audit/hooks';
import { useCreateAuditExport } from '@/features/reports/hooks';
import { useSession } from '@/features/auth/session';
import { formatDateTime, humanize } from '@/lib/format';
import type { AuditLog } from '@/lib/types';

const CATEGORIES = ['AUTH', 'ATTENDANCE', 'TASK', 'ORDER', 'LEAVE', 'LEDGER', 'PAYROLL', 'COMPLAINT', 'SETTINGS', 'PERMISSION', 'SECURITY', 'EMPLOYEE'];

export default function AdminAuditPage() {
  const { settings } = useSession();
  const [filters, setFilters] = useState({ category: '', action: '', entity_type: '', entity_id: '', from: '', to: '' });
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.length > 0 ? cursors[cursors.length - 1] : undefined;
  const query = useAuditLogs({ ...filters, cursor });

  const exportAudit = useCreateAuditExport();
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [format, setFormat] = useState('CSV');

  const exportedFormats = (() => {
    const value = settings.report_export_formats;
    if (Array.isArray(value)) return value.map(String);
    return ['CSV', 'XLSX'];
  })();

  const columns: Array<Column<AuditLog>> = [
    { key: 'created_at', header: 'When', render: (row) => formatDateTime(row.created_at) },
    { key: 'category', header: 'Category', render: (row) => humanize(row.category) },
    { key: 'action', header: 'Action', render: (row) => row.action },
    { key: 'entity', header: 'Entity', render: (row) => (row.entity_type ? humanize(row.entity_type) : '-') },
    { key: 'actor', header: 'Actor', render: (row) => row.actor?.username ?? (row.actor_user_id ? row.actor_user_id.slice(0, 8) : 'system') },
    { key: 'reason', header: 'Reason', render: (row) => <span className="text-content-muted">{row.reason ?? '-'}</span> }
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Audit log"
        description="Immutable record of important changes. Records cannot be edited or deleted through the API."
        actions={
          <PermissionGate anyOf={['audit.export']}>
            <Button variant="secondary" onClick={() => setExportOpen(true)}>Export</Button>
          </PermissionGate>
        }
      />

      <Card>
        <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SelectField
            label="Category"
            name="category"
            placeholder="Any"
            value={filters.category}
            onChange={(event) => { setFilters({ ...filters, category: event.target.value }); setCursors([]); }}
            options={CATEGORIES.map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField label="Action" name="action" value={filters.action} onChange={(event) => { setFilters({ ...filters, action: event.target.value }); setCursors([]); }} />
          <TextField label="Entity type" name="entity_type" value={filters.entity_type} onChange={(event) => { setFilters({ ...filters, entity_type: event.target.value }); setCursors([]); }} />
          <TextField label="Entity id" name="entity_id" value={filters.entity_id} onChange={(event) => { setFilters({ ...filters, entity_id: event.target.value }); setCursors([]); }} />
          <TextField label="From" name="from" type="date" value={filters.from} onChange={(event) => { setFilters({ ...filters, from: event.target.value }); setCursors([]); }} />
          <TextField label="To" name="to" type="date" value={filters.to} onChange={(event) => { setFilters({ ...filters, to: event.target.value }); setCursors([]); }} />
        </CardBody>
      </Card>

      <DataTable
        columns={columns}
        rows={query.data?.items ?? []}
        getRowId={(row) => row.id}
        loading={query.isLoading}
        error={query.error ? <ProblemAlert error={query.error} onRetry={() => void query.refetch()} /> : undefined}
        onRowClick={(row) => setSelected(row)}
        emptyTitle="No audit records"
        emptyHint="Nothing matches these filters."
        testId="audit-table"
      />

      <div className="flex items-center justify-between gap-3">
        <Button
          variant="secondary"
          disabled={cursors.length === 0}
          onClick={() => setCursors((current) => current.slice(0, Math.max(0, current.length - 1)))}
        >
          Previous page
        </Button>
        <Button
          variant="secondary"
          disabled={!query.data?.next_cursor}
          onClick={() => {
            const next = (query.data as { next_cursor?: string | null } | undefined)?.next_cursor;
            if (next) setCursors((current) => [...current, next]);
          }}
        >
          Next page
        </Button>
      </div>

      <Dialog
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title="Audit record"
        description="Before/after values rendered as a diff."
      >
        {selected ? (
          <div className="space-y-3 text-sm">
            <dl className="space-y-2">
              <div className="flex justify-between gap-3"><dt className="text-content-muted">When</dt><dd>{formatDateTime(selected.created_at)}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Category</dt><dd>{humanize(selected.category)}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Action</dt><dd>{selected.action}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Entity</dt><dd>{selected.entity_type ? `${humanize(selected.entity_type)} ${selected.entity_id ?? ''}` : '-'}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Actor</dt><dd>{selected.actor?.username ?? selected.actor_user_id ?? 'system'}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Status</dt><dd><StatusPill value={selected.category} /></dd></div>
              {selected.reason ? <div className="flex justify-between gap-3"><dt className="text-content-muted">Reason</dt><dd className="text-right">{selected.reason}</dd></div> : null}
              {selected.request_id ? <div className="flex justify-between gap-3"><dt className="text-content-muted">Request</dt><dd className="font-mono text-xs">{selected.request_id}</dd></div> : null}
            </dl>
            <SelectiveFields before={selected.before} after={selected.after} />
          </div>
        ) : null}
      </Dialog>

      <Dialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        title="Export audit records"
        description="The export applies the filters currently set on this screen."
        footer={
          <>
            <Button variant="secondary" onClick={() => setExportOpen(false)}>Cancel</Button>
            <Button
              loading={exportAudit.isPending}
              disabled={exportAudit.isPending}
              onClick={() =>
                exportAudit.mutate({ format, filters }, { onSuccess: () => setExportOpen(false) })
              }
            >
              Queue export
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {exportAudit.error ? <ProblemAlert error={exportAudit.error} /> : null}
          <SelectField
            label="Format"
            name="format"
            required
            value={format}
            onChange={(event) => setFormat(event.target.value)}
            options={exportedFormats.map((value) => ({ value, label: value }))}
          />
        </div>
      </Dialog>
    </div>
  );
}