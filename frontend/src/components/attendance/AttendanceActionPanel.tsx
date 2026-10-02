'use client';

import { useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatTime, humanize } from '@/lib/format';
import { useIdempotency } from '@/lib/idempotency';
import { useSession } from '@/features/auth/session';
import { useBreakTypes, useCheckIn, useCheckOut, useEndBreak, useStartBreak, useTodayAttendance } from '@/features/attendance/hooks';
import { LocationError, getCurrentLocation, locationPermissionState, type LocationFix } from '@/features/attendance/geolocation';
import type { AttendanceAction, AttendanceEvidenceRequirement, AttendanceRecord, AttendanceVerificationMode, BreakType, VerificationResult } from '@/lib/types';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Dialog } from '@/components/ui/Dialog';
import { SelectField } from '@/components/ui/Form';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { QrScanner } from './QrScanner';

type Phase = 'idle' | 'running' | 'scanning' | 'done';

interface Outcome {
  tone: 'success' | 'error';
  verification?: VerificationResult | null;
  error?: unknown;
}

const ACTION_LABEL: Record<AttendanceAction, string> = {
  CHECK_IN: 'Check in',
  CHECK_OUT: 'Check out',
  START_BREAK: 'Start break',
  END_BREAK: 'End break',
  REQUEST_CORRECTION: 'Request correction'
};

const PROGRESS_STEPS = ['Getting location', 'Checking geofence', 'Verifying QR', 'Confirming with server'];

/**
 * Resolve the evidence requirement for DISPLAY. The authoritative requirement is
 * `record.required_evidence` from the server; the session setting is only a display fallback and
 * is never used to decide whether attendance is valid (docs/07_UI_SPEC.md section 8 rule 1).
 */
function resolveRequirement(
  record: AttendanceRecord,
  settingsMode: AttendanceVerificationMode | undefined
): AttendanceEvidenceRequirement {
  if (record.required_evidence) return record.required_evidence;
  const mode = settingsMode ?? 'NONE';
  return {
    mode,
    location_required: mode === 'GPS' || mode === 'GPS_AND_QR' || mode === 'GPS_OR_QR',
    qr_required: mode === 'QR' || mode === 'GPS_AND_QR'
  };
}

export function AttendanceActionPanel({ record }: { record: AttendanceRecord }) {
  const { settings } = useSession();
  const { refetch } = useTodayAttendance();
  const checkIn = useCheckIn();
  const checkOut = useCheckOut();
  const startBreak = useStartBreak();
  const endBreak = useEndBreak();
  const breakTypes = useBreakTypes();
  const breakTypeList: BreakType[] = breakTypes.data?.items ?? [];

  const idem = useIdempotency();
  const locationRef = useRef<LocationFix | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [progressIndex, setProgressIndex] = useState<number>(-1);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [breakDialogOpen, setBreakDialogOpen] = useState(false);
  const [breakTypeId, setBreakTypeId] = useState('');
  const [prePermission, setPrePermission] = useState(false);

  const action = record.next_allowed_action ?? null;
  const requirement = useMemo(
    () => resolveRequirement(record, settings.attendance_verification_mode as AttendanceVerificationMode | undefined),
    [record, settings.attendance_verification_mode]
  );

  const busy = phase === 'running' || phase === 'scanning';
  const openBreak = record.open_break ?? null;

  function buildEvidence(location: LocationFix | null, qrToken: string | null): Record<string, unknown> {
    const evidence: Record<string, unknown> = { client_time: new Date().toISOString(), device_info: navigator.userAgent.slice(0, 200) };
    if (location) {
      evidence.latitude = location.latitude;
      evidence.longitude = location.longitude;
      evidence.accuracy_meters = location.accuracy_meters;
      evidence.location_captured_at = location.location_captured_at;
    }
    if (qrToken) evidence.qr_token = qrToken;
    return evidence;
  }

  function presentFailure(error: unknown) {
    setOutcome({ tone: 'error', error });
    setPhase('done');
    setProgressIndex(-1);
    void refetch();
  }

  async function submitWithEvidence(location: LocationFix | null, qrToken: string | null) {
    if (!action) return;
    setPhase('running');
    setProgressIndex(PROGRESS_STEPS.length - 1);
    try {
      const evidence = buildEvidence(location, qrToken);
      const result =
        action === 'CHECK_IN'
          ? await checkIn.mutateAsync({ evidence, idempotencyKey: idem.key() })
          : await checkOut.mutateAsync({ evidence, idempotencyKey: idem.key() });
      idem.reset();
      setOutcome({ tone: 'success', verification: result.verification ?? null });
      setPhase('done');
      setProgressIndex(-1);
      await refetch();
    } catch (error) {
      presentFailure(error);
    }
  }

  async function startEvidenceFlow() {
    setOutcome(null);
    setPrePermission(false);
    locationRef.current = null;

    if (requirement.location_required) {
      const permission = await locationPermissionState();
      if (permission === 'prompt') {
        setPrePermission(true);
      }
      setPhase('running');
      setProgressIndex(0);
      try {
        const fix = await getCurrentLocation();
        locationRef.current = fix;
      } catch (error) {
        if (!requirement.qr_required && requirement.mode === 'GPS') {
          if (error instanceof LocationError) {
            presentFailure(
              new ApiError(
                { title: error.message, code: error.code, status: 422, rule_code: error.code, detail: error.message },
                null
              )
            );
          } else {
            presentFailure(error);
          }
          return;
        }
        // Fallback gracefully to Dynamic QR mode if QR is available or as fallback
        setPrePermission(false);
      }
    } else {
      setPhase('running');
    }

    setProgressIndex(1);
    // If QR is required OR if location was required (fallback to QR for seamless check-in)
    if (requirement.qr_required || (requirement.location_required && !locationRef.current)) {
      setProgressIndex(2);
      setPhase('scanning');
      return;
    }

    await submitWithEvidence(locationRef.current, null);
  }

  async function handlePrimary() {
    if (!action) return;
    if (action === 'CHECK_IN' || action === 'CHECK_OUT') {
      await startEvidenceFlow();
      return;
    }
    if (action === 'START_BREAK') {
      setBreakDialogOpen(true);
      return;
    }
    if (action === 'END_BREAK') {
      setOutcome(null);
      setPhase('running');
      try {
        await endBreak.mutateAsync(idem.key());
        idem.reset();
        setOutcome({ tone: 'success' });
        setPhase('done');
        await refetch();
      } catch (error) {
        presentFailure(error);
      }
    }
  }

  async function handleStartBreak() {
    if (!breakTypeId) return;
    setBreakDialogOpen(false);
    setOutcome(null);
    setPhase('running');
    try {
      await startBreak.mutateAsync({ breakTypeId, idempotencyKey: idem.key() });
      idem.reset();
      setOutcome({ tone: 'success' });
      setPhase('done');
      await refetch();
    } catch (error) {
      presentFailure(error);
    } finally {
      setPhase((current) => (current === 'running' ? 'done' : current));
    }
  }

  const showEvidenceHints = requirement.location_required || requirement.qr_required;

  return (
    <section aria-labelledby="attendance-action-heading" className="space-y-3" data-testid="attendance-action-panel">
      <div className="flex items-center justify-between gap-2">
        <h2 id="attendance-action-heading" className="text-sm font-semibold text-content">
          Today
        </h2>
        {action ? <Badge tone="primary">{ACTION_LABEL[action]}</Badge> : <Badge tone="neutral">Day complete</Badge>}
      </div>

      {showEvidenceHints ? (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-content-muted">
          {requirement.location_required ? (
            <span className="rounded bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
              GPS: Coming Soon
            </span>
          ) : null}
          <span className="rounded bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 dark:bg-blue-950/40 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
            Dynamic QR Code Active
          </span>
        </p>
      ) : null}

      {openBreak ? (
        <p className="text-xs text-warning">
          A {openBreak.break_type?.name ?? 'break'} started at {formatTime(openBreak.started_at, settings.business_timezone)} is still open.
        </p>
      ) : null}

      {prePermission && phase === 'running' ? (
        <Alert
          tone="info"
          title="We need your location for this attendance action only."
          nextStep="Allow the browser prompt. Location is never tracked continuously."
        />
      ) : null}

      {phase === 'running' || phase === 'scanning' ? (
        <ol aria-live="polite" className="space-y-1 text-sm" data-testid="attendance-progress">
          {PROGRESS_STEPS.filter((step) => {
            if (step === 'Getting location') return requirement.location_required;
            if (step === 'Checking geofence') return requirement.location_required;
            if (step === 'Verifying QR') return requirement.qr_required;
            return true;
          }).map((step) => (
            <li key={step} className="flex items-center gap-2">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-primary" />
              <span className="text-content-muted">{step}</span>
            </li>
          ))}
          {progressIndex >= 0 ? <li className="sr-only">Current step: {PROGRESS_STEPS[progressIndex]}</li> : null}
        </ol>
      ) : null}

      {phase === 'scanning' ? (
        <Dialog open onClose={() => setPhase('idle')} title="Scan the shop QR code" description="Point the camera at the code shown on the shop display.">
          <QrScanner
            onScan={(payload) => {
              setPhase('running');
              void submitWithEvidence(locationRef.current, payload);
            }}
            onCancel={() => setPhase('idle')}
          />
        </Dialog>
      ) : null}

      {outcome?.tone === 'success' ? (
        <Alert
          tone="success"
          title={`Confirmed by the server: ${humanize(action ?? record.status)}`}
          testId="attendance-success"
        >
          <p>
            Recorded at {formatTime(action === 'CHECK_IN' ? record.first_check_in_at : record.last_check_out_at, settings.business_timezone) || 'the server time'}.
          </p>
          {outcome.verification ? (
            <p className="mt-1 text-xs">
              Method {humanize(outcome.verification.method)} - result {humanize(outcome.verification.result)}
              {outcome.verification.distance_meters !== null ? ` - ${Math.round(outcome.verification.distance_meters)} m from shop` : ''}
            </p>
          ) : null}
        </Alert>
      ) : null}

      {outcome?.tone === 'error' ? (
        <ProblemAlert
          error={outcome.error}
          testId="attendance-error"
          onRetry={() => {
            setOutcome(null);
            setPhase('idle');
          }}
        />
      ) : null}

      {action === 'REQUEST_CORRECTION' ? (
        <div className="space-y-2">
          <Link
            href="/app/attendance/corrections"
            className="inline-flex min-h-touch items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-fg"
          >
            Request an attendance correction
          </Link>
          <p className="text-xs text-content-muted">
            Your day is closed or incomplete. A correction is the only way to change a recorded attendance value.
          </p>
        </div>
      ) : null}

      {action && action !== 'REQUEST_CORRECTION' ? (
        <Button
          size="action"
          onClick={() => void handlePrimary()}
          loading={busy}
          loadingLabel="Working"
          disabled={busy || (action === 'START_BREAK' && breakTypeList.length === 0)}
          data-testid={`attendance-${action.toLowerCase().replace(/_/g, '-')}-button`}
        >
          {ACTION_LABEL[action]}
        </Button>
      ) : null}

      {action === 'START_BREAK' && breakTypeList.length === 0 && !breakTypes.isLoading ? (
        <p className="text-xs text-content-muted">No break types are configured. Ask the admin to add one.</p>
      ) : null}

      <Dialog
        open={breakDialogOpen}
        onClose={() => setBreakDialogOpen(false)}
        title="Start a break"
        description="Choose the break type. The server validates the session state and any daily cap."
        footer={
          <>
            <Button variant="secondary" onClick={() => setBreakDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleStartBreak()} disabled={!breakTypeId || startBreak.isPending} loading={startBreak.isPending}>
              Start break
            </Button>
          </>
        }
      >
        <SelectField
          label="Break type"
          name="break_type_id"
          placeholder="Select a break type"
          value={breakTypeId}
          onChange={(event) => setBreakTypeId(event.target.value)}
          options={breakTypeList.map((type) => ({
            value: type.id,
            label: `${type.name}${type.is_paid ? '' : ' (unpaid)'}`
          }))}
        />
      </Dialog>
    </section>
  );
}