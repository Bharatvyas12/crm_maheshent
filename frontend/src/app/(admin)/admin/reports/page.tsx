'use client';

import { useState } from 'react';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { SelectField, TextField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { useCreateExport, useDeleteExportJob, useExports, useReport, useReportCatalog } from '@/features/reports/hooks';
import { useSettings } from '@/features/settings/hooks';
import { formatDateTime, formatMoney, humanize } from '@/lib/format';
import type { ExportJob, ReportCatalogItem } from '@/lib/types';

type Row = Record<string, unknown>;

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'string' && /^\d+(\.\d+)?$/.test(value) && value.includes('.')) return value;
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function AdminReportsPage() {
  const catalog = useReportCatalog();
  const settings = useSettings();
  const exportsQuery = useExports();
  const createExport = useCreateExport();
  const deleteExport = useDeleteExportJob();

  const [reportType, setReportType] = useState<string>('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [exportOpen, setExportOpen] = useState(false);
  const [format, setFormat] = useState('');

  const selected: ReportCatalogItem | undefined = catalog.data?.items.find((item) => item.report_type === reportType);
  const report = useReport(selected ? (selected.report_type as never) : null, { ...values, page });

  const exportFormats = (() => {
    const setting = settings.data?.items.find((item) => item.key === 'reports.export_formats');
    if (Array.isArray(setting?.value)) return setting.value.map(String);
    if (selected?.formats?.length) return selected.formats;
    return ['CSV', 'XLSX'];
  })();

  const rows: Row[] = report.data?.items ?? [];
  const columns: Array<Column<Row>> = rows.length > 0
    ? Object.keys(rows[0]).map((key) => ({
        key,
        header: humanize(key),
        render: (row: Row) => renderCell(row[key])
      }))
    : [];

  const exportColumns: Array<Column<ExportJob>> = [
    { key: 'report_type', header: 'Report', render: (row) => humanize(row.report_type) },
    { key: 'format', header: 'Format', render: (row) => row.format },
    { key: 'status', header: 'Status', render: (row) => <StatusPill value={row.status} /> },
    { key: 'created_at', header: 'Requested', render: (row) => formatDateTime(row.created_at) },
    {
      key: 'download',
      header: '',
      render: (row) =>
        row.download_url ? (
          <a href={row.download_url} className="text-sm font-medium text-primary hover:underline" target="_blank" rel="noreferrer">
            Download
          </a>
        ) : (
          <span className="text-xs text-content-muted">{row.error_message ?? 'Generating'}</span>
        )
    },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Button variant="link" size="sm" onClick={() => deleteExport.mutate(row.id)}>
          Remove
        </Button>
      )
    }
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Reports"
        description="Every number is aggregated by the server. Filters are the ones the report defines."
        actions={
          <PermissionGate anyOf={['report.export']}>
            <Button disabled={!selected} onClick={() => { setFormat(exportFormats[0] ?? 'CSV'); setExportOpen(true); }}>
              Export
            </Button>
          </PermissionGate>
        }
      />

      <Card>
        <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SelectField
            label="Report"
            name="report_type"
            placeholder={catalog.isLoading ? 'Loading reports...' : 'Choose a report'}
            value={reportType}
            onChange={(event) => { setReportType(event.target.value); setValues({}); setPage(1); }}
            options={(catalog.data?.items ?? []).map((item) => ({ value: item.report_type, label: item.name }))}
          />
          {(selected?.filters ?? []).map((filter) => (
            <TextField
              key={filter.name}
              label={filter.label}
              name={filter.name}
              type={filter.type === 'date' ? 'date' : filter.type === 'number' ? 'number' : 'text'}
              required={filter.required}
              value={values[filter.name] ?? ''}
              onChange={(event) => { setValues((current) => ({ ...current, [filter.name]: event.target.value })); setPage(1); }}
            />
          ))}
        </CardBody>
        {selected?.description ? <p className="px-4 pb-4 text-xs text-content-muted">{selected.description}</p> : null}
      </Card>

      {catalog.error ? <ProblemAlert error={catalog.error} onRetry={() => void catalog.refetch()} /> : null}

      {!reportType ? (
        <EmptyState title="Choose a report" hint="Pick a report above to load its filters and rows." />
      ) : report.isLoading ? (
        <SkeletonList rows={6} />
      ) : report.error ? (
        <ProblemAlert error={report.error} onRetry={() => void report.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title="No rows for these filters" hint="Adjust the date range or filters and run the report again." />
      ) : (
        <>
          <DataTable columns={columns} rows={rows} getRowId={(row) => String(row.id ?? JSON.stringify(row))} caption={`${selected?.name ?? 'Report'} rows`} />
          {report.data ? (
            <Pagination
              page={Number(report.data.page ?? page)}
              pageSize={Number(report.data.page_size ?? 20)}
              totalItems={Number(report.data.total_items ?? rows.length)}
              totalPages={Number(report.data.total_pages ?? 1)}
              onPageChange={setPage}
            />
          ) : null}
          {report.data?.totals ? (
            <Card>
              <CardHeader>
                <CardTitle as="h2">Totals</CardTitle>
              </CardHeader>
              <CardBody className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                {Object.entries(report.data.totals).map(([key, value]) => (
                  <div key={key}>
                    <p className="text-xs uppercase tracking-wide text-content-muted">{humanize(key)}</p>
                    <p className="font-medium">
                      {typeof value === 'string' && /^\d+\.\d{2}$/.test(value) ? formatMoney(value) : renderCell(value)}
                    </p>
                  </div>
                ))}
              </CardBody>
            </Card>
          ) : null}
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Exports</CardTitle>
        </CardHeader>
        <CardBody>
          <DataTable
            columns={exportColumns}
            rows={exportsQuery.data?.items ?? []}
            getRowId={(row) => row.id}
            loading={exportsQuery.isLoading}
            error={exportsQuery.error ? <ProblemAlert error={exportsQuery.error} onRetry={() => void exportsQuery.refetch()} /> : undefined}
            emptyTitle="No export jobs"
            emptyHint="Requested exports appear here with a download link once they complete."
            testId="exports-table"
          />
        </CardBody>
      </Card>

      <Dialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        title="Export this report"
        description="Exports run in the background and stream from object storage. Identical jobs are de-duplicated."
        footer={
          <>
            <Button variant="secondary" onClick={() => setExportOpen(false)}>Cancel</Button>
            <Button
              loading={createExport.isPending}
              disabled={!format || createExport.isPending}
              onClick={() => {
                if (!selected) return;
                createExport.mutate(
                  { report_type: selected.report_type, format, parameters: values },
                  { onSuccess: () => setExportOpen(false) }
                );
              }}
            >
              Queue export
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {createExport.error ? <ProblemAlert error={createExport.error} /> : null}
          <SelectField
            label="Format"
            name="format"
            required
            value={format}
            onChange={(event) => setFormat(event.target.value)}
            options={exportFormats.map((value) => ({ value, label: value }))}
          />
        </div>
      </Dialog>
    </div>
  );
}