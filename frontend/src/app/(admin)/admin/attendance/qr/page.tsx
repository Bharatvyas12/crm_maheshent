'use client';

import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { ApiError } from '@/lib/api-client';
import { useIssueQrToken } from '@/features/attendance/hooks';
import { formatCountdown, formatDateTime } from '@/lib/format';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { SelectField } from '@/components/ui/Form';
import { SkeletonList } from '@/components/ui/Skeleton';

const PURPOSES = [
  { value: 'SHOP_CHECKIN', label: 'Check-in' },
  { value: 'SHOP_CHECKOUT', label: 'Check-out' }
];

/**
 * Full-screen, high-contrast shop display with an auto-rotating code and a countdown
 * (docs/07_UI_SPEC.md section 7.2).
 *
 * The token is issued by `POST /attendance/qr-tokens`; the image is rendered client-side from the
 * server-provided `qr_payload` so no undocumented endpoint is required. Rotation follows the
 * server's `rotation_seconds` / `expires_at`.
 */
export default function AdminQrDisplayPage() {
  const [purpose, setPurpose] = useState('SHOP_CHECKIN');
  const issue = useIssueQrToken();
  const [now, setNow] = useState(() => new Date());
  const [autoRotate, setAutoRotate] = useState(true);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const token = issue.data ?? null;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    void issue.mutateAsync(purpose).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purpose]);

  useEffect(() => {
    if (!token?.qr_payload) {
      setImageUrl(null);
      return;
    }
    let cancelled = false;
    QRCode.toDataURL(token.qr_payload, { margin: 2, width: 320, errorCorrectionLevel: 'M' })
      .then((url) => {
        if (!cancelled) {
          setImageUrl(url);
          setRenderError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setImageUrl(null);
          setRenderError('The code could not be rendered. The payload is shown below so it can still be scanned or regenerated.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token?.qr_payload]);

  const countdown = token ? formatCountdown(token.expires_at, now) : null;
  const expired = Boolean(token) && countdown === null;

  useEffect(() => {
    if (!autoRotate || !token || !expired) return;
    void issue.mutateAsync(purpose).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRotate, expired, token, purpose]);

  const error = issue.error instanceof ApiError ? issue.error : null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Shop QR display"
        description="Show this on the shop device. The code rotates; scanning it is one part of attendance verification."
        actions={
          <Button variant="secondary" loading={issue.isPending} onClick={() => void issue.mutateAsync(purpose)}>
            Rotate now
          </Button>
        }
      />

      {error ? (
        <Alert
          tone="danger"
          title="The token could not be issued."
          nextStep="Check the QR settings and try again; employees cannot verify by QR until this works."
        />
      ) : null}

      <Card>
        <CardBody className="flex flex-wrap items-end gap-3">
          <SelectField
            label="Purpose"
            name="purpose"
            containerClassName="w-48"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            options={PURPOSES}
          />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-5 w-5" checked={autoRotate} onChange={(e) => setAutoRotate(e.target.checked)} />
            Auto-rotate when it expires
          </label>
        </CardBody>
      </Card>

      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 rounded-card border border-surface-border bg-white p-6">
        {issue.isPending && !token ? (
          <SkeletonList rows={2} />
        ) : token ? (
          <>
            <div className="rounded-md border-4 border-black p-4">
              <div className="flex h-64 w-64 items-center justify-center bg-white text-center">
                {imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={imageUrl} alt="Shop attendance QR code" className="h-64 w-64" />
                ) : (
                  <p className="p-4 text-xs text-content-muted">Rendering the code...</p>
                )}
              </div>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold tabular-nums text-black">{countdown ?? 'Expired'}</p>
              <p className="mt-1 text-sm text-content-muted">Expires {formatDateTime(token.expires_at)}</p>
              {renderError ? <p className="mt-2 max-w-md text-xs text-warning">{renderError}</p> : null}
              <p className="mt-2 max-w-xl break-all font-mono text-xs text-content-muted">{token.qr_payload.slice(0, 80)}...</p>
            </div>
          </>
        ) : (
          <p className="text-sm text-content-muted">No token issued yet.</p>
        )}
      </div>
    </div>
  );
}