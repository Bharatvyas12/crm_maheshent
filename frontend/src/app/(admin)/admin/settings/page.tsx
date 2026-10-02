'use client';

import { useMemo, useState } from 'react';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { Dialog } from '@/components/ui/Dialog';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { CheckboxField, SelectField, Switch, TextAreaField, TextField } from '@/components/ui/Form';
import { SkeletonList } from '@/components/ui/Skeleton';
import { useSettingHistory, useSettings, useSettingsSchema, useUpdateSettings } from '@/features/settings/hooks';
import { formatDateTime, humanize } from '@/lib/format';
import type { SettingSchemaItem } from '@/lib/types';

/**
 * Settings forms are generated from GET /settings/schema (docs/07_UI_SPEC.md section 7.4).
 * Nothing here hard-codes a threshold, a label or a bound: they all come from the registry.
 */

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.map(String).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function parseValue(schema: SettingSchemaItem, raw: string): unknown {
  if (schema.value_type === 'BOOLEAN') return raw === 'true';
  if (schema.value_type === 'INTEGER') return Number.parseInt(raw, 10);
  if (schema.value_type === 'NUMBER' || schema.value_type === 'DURATION') return raw;
  if (schema.value_type === 'JSON_LIST') {
    return raw
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => (Number.isNaN(Number(part)) ? part : Number(part)));
  }
  return raw;
}

function humanizeSettingKey(key: string): string {
  const parts = key.split('.');
  const name = parts[parts.length - 1];
  return name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function SettingControl({
  schema,
  value,
  onChange
}: {
  schema: SettingSchemaItem;
  value: string;
  onChange: (next: string) => void;
}) {
  const label = humanizeSettingKey(schema.key);
  const help = [
    schema.description,
    schema.unit ? `Unit: ${schema.unit}` : null,
    schema.min !== null || schema.max !== null ? `Allowed range: ${schema.min ?? '-'} to ${schema.max ?? '-'}` : null
  ]
    .filter(Boolean)
    .join(' · ');

  if (schema.value_type === 'BOOLEAN') {
    return (
      <div>
        <Switch label={label} checked={value === 'true'} onChange={(next) => onChange(next ? 'true' : 'false')} name={schema.key} />
        {help ? <p className="mt-1 text-xs text-content-muted">{help}</p> : null}
      </div>
    );
  }

  if (schema.value_type === 'ENUM' && Array.isArray(schema.allowed_values)) {
    return (
      <SelectField
        label={label}
        name={schema.key}
        help={help}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        options={schema.allowed_values.map((option) => ({ value: String(option), label: String(option) }))}
      />
    );
  }

  const inputType =
    schema.value_type === 'TIME' ? 'time' : schema.value_type === 'INTEGER' || schema.value_type === 'NUMBER' || schema.value_type === 'DURATION' ? 'number' : 'text';

  return (
    <TextField
      label={label}
      name={schema.key}
      type={inputType}
      help={help}
      inputMode={schema.value_type === 'NUMBER' ? 'decimal' : undefined}
      min={schema.min ?? undefined}
      max={schema.max ?? undefined}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function HistoryDialog({ settingKey, onClose }: { settingKey: string; onClose: () => void }) {
  const history = useSettingHistory(settingKey, true);
  return (
    <Dialog open onClose={onClose} title={`History - ${humanizeSettingKey(settingKey)}`} description={`Key: ${settingKey} · Who changed what, when and why.`}>
      {history.isLoading ? (
        <SkeletonList rows={3} />
      ) : history.error ? (
        <ProblemAlert error={history.error} onRetry={() => void history.refetch()} />
      ) : (history.data?.items.length ?? 0) === 0 ? (
        <p className="text-sm text-content-muted">No changes recorded for this setting yet.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {history.data?.items.map((entry) => (
            <li key={entry.id} className="rounded-md border border-surface-border p-2">
              <p className="text-xs text-content-muted">{formatDateTime(entry.created_at)}</p>
              <p>
                <span className="text-content-muted">{displayValue(entry.old_value)}</span>
                {' -> '}
                <span className="font-medium">{displayValue(entry.new_value)}</span>
              </p>
              <p className="text-xs text-content-muted">Reason: {entry.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

export default function AdminSettingsPage() {
  const schema = useSettingsSchema();
  const current = useSettings();
  const update = useUpdateSettings();

  const [group, setGroup] = useState('');
  const [search, setSearch] = useState('');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [reason, setReason] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [historyKey, setHistoryKey] = useState('');

  const schemaItems = useMemo(() => (Array.isArray(schema.data?.items) ? schema.data.items : []), [schema.data]);

  const groups = useMemo(() => {
    const set = new Set<string>();
    for (const item of schemaItems) set.add(item.group);
    return Array.from(set).sort();
  }, [schemaItems]);

  const visible = schemaItems.filter((item) => {
    if (group && item.group !== group) return false;
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      const label = humanizeSettingKey(item.key).toLowerCase();
      const desc = (item.description || '').toLowerCase();
      const k = item.key.toLowerCase();
      return label.includes(q) || desc.includes(q) || k.includes(q);
    }
    return true;
  });

  const changed = visible
    .filter((item) => drafts[item.key] !== undefined)
    .map((item) => {
      const stored = current.data?.items.find((setting) => setting.key === item.key);
      const original = displayValue(stored?.value ?? item.default);
      return { schema: item, original, next: drafts[item.key] };
    })
    .filter((entry) => entry.original !== entry.next);

  const historyAffecting = changed.filter((entry) => entry.schema.affects_history === true);

  function save() {
    setError(null);
    update.mutate(
      { reason: reason.trim(), changes: changed.map((entry) => ({ key: entry.schema.key, value: parseValue(entry.schema, entry.next) })) },
      {
        onSuccess: () => {
          setDrafts({});
          setReason('');
          setAcknowledged(false);
          setSaveOpen(false);
        },
        onError: setError
      }
    );
  }

  const canSave = changed.length > 0 && reason.trim().length > 0 && (historyAffecting.length === 0 || acknowledged);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Settings"
        description="Review and configure main business rules, shift timings, break policies, and system settings."
      />

      {update.isSuccess && !saveOpen ? <Alert tone="success" title="Settings saved successfully" /> : null}

      <Card>
        <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <SelectField
            label="Category"
            name="group"
            placeholder="All Categories"
            value={group}
            onChange={(event) => setGroup(event.target.value)}
            options={groups.map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField
            label="Search setting"
            name="search"
            placeholder="Search by name, key, or description..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </CardBody>
      </Card>

      {schema.isLoading || current.isLoading ? (
        <SkeletonList rows={6} />
      ) : schema.error ? (
        <ProblemAlert error={schema.error} onRetry={() => void schema.refetch()} />
      ) : current.error ? (
        <ProblemAlert error={current.error} onRetry={() => void current.refetch()} />
      ) : visible.length === 0 ? (
        <Card>
          <CardBody>
            <p className="text-center text-sm text-content-muted py-6">No settings matched your filter.</p>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-4">
          {Array.from(new Set(visible.map((item) => item.group))).map((groupName) => (
            <Card key={groupName}>
              <CardHeader>
                <CardTitle as="h2">{humanize(groupName)} Settings</CardTitle>
              </CardHeader>
              <CardBody className="space-y-6">
                {visible
                  .filter((item) => item.group === groupName)
                  .map((item) => {
                    const stored = current.data?.items.find((setting) => setting.key === item.key);
                    const value = drafts[item.key] ?? displayValue(stored?.value ?? item.default);
                    const modified = drafts[item.key] !== undefined && drafts[item.key] !== displayValue(stored?.value ?? item.default);
                    return (
                      <div key={item.key} className={modified ? 'rounded-lg border border-primary/50 bg-primary-soft/10 p-3' : undefined}>
                        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-mono text-content-muted bg-surface-muted px-1.5 py-0.5 rounded border border-border/40">
                              {item.key}
                            </span>
                            {item.is_provisional ? <Badge tone="warning">Provisional - awaiting confirmation</Badge> : null}
                          </div>
                          <PermissionGate anyOf={['settings.read.history']}>
                            <Button variant="link" size="sm" onClick={() => setHistoryKey(item.key)}>
                              View History
                            </Button>
                          </PermissionGate>
                        </div>
                        <SettingControl
                          schema={item}
                          value={value}
                          onChange={(next) => setDrafts((currentDrafts) => ({ ...currentDrafts, [item.key]: next }))}
                        />
                      </div>
                    );
                  })}
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <div className="sticky bottom-0 flex flex-wrap items-center gap-3 border-t border-surface-border bg-surface px-4 py-3">
        <p className="text-sm text-content-muted">{changed.length} unsaved change(s)</p>
        <PermissionGate anyOf={['settings.update']}>
          <Button disabled={changed.length === 0} onClick={() => setSaveOpen(true)}>
            Review and save
          </Button>
        </PermissionGate>
      </div>

      <Dialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        title="Review changes"
        description="Every save requires a reason and records a before/after history entry."
        footer={
          <>
            <Button variant="secondary" onClick={() => setSaveOpen(false)}>Cancel</Button>
            <Button loading={update.isPending} disabled={!canSave || update.isPending} onClick={save}>
              Save changes
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {error ? <ProblemAlert error={error} /> : null}
          <ul className="space-y-1 text-sm">
            {changed.map((entry) => (
              <li key={entry.schema.key} className="rounded-md border border-surface-border p-2">
                <p className="font-medium">{entry.schema.key}</p>
                <p>
                  <span className="text-content-muted">{entry.original || '(empty)'}</span>
                  {' -> '}
                  <span className="font-medium">{entry.next || '(empty)'}</span>
                </p>
              </li>
            ))}
          </ul>
          {historyAffecting.length > 0 ? (
            <Alert tone="warning" title="This change affects already-computed attendance or payroll.">
              Existing records are not rewritten. Confirm that you understand the affected dates before saving.
            </Alert>
          ) : null}
          {historyAffecting.length > 0 ? (
            <CheckboxField
              label="I understand this affects historical computations"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
          ) : null}
          <TextAreaField
            label="Reason (required)"
            name="reason"
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      </Dialog>

      {historyKey ? <HistoryDialog settingKey={historyKey} onClose={() => setHistoryKey('')} /> : null}
    </div>
  );
}