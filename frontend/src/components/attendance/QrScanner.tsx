'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Form';
import { Alert } from '@/components/ui/Alert';

interface DetectedBarcode {
  rawValue: string;
}

interface BarcodeDetectorLike {
  detect(source: HTMLVideoElement): Promise<DetectedBarcode[]>;
}

type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

type ScannerStatus = 'starting' | 'scanning' | 'unsupported' | 'denied' | 'error';

/**
 * Dynamic shop-QR scanner (docs/07_UI_SPEC.md section 6.2 step 4 and section 8 rule 4).
 *
 * Uses the native `BarcodeDetector` API when the browser provides it (Chrome/Android PWA). When
 * it is unavailable the user can type/paste the code shown on the shop display, so the flow is
 * never a dead end. The decoded value is only ever sent to the server for evaluation.
 */
export function QrScanner({
  onScan,
  onCancel
}: {
  onScan: (payload: string) => void;
  onCancel: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const [status, setStatus] = useState<ScannerStatus>('starting');
  const [manual, setManual] = useState('');
  const [scanned, setScanned] = useState<string | null>(null);

  const stop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      const globalWithDetector = window as unknown as { BarcodeDetector?: BarcodeDetectorCtor };
      if (!globalWithDetector.BarcodeDetector) {
        setStatus('unsupported');
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus('unsupported');
        return;
      }

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      } catch (error) {
        const name = (error as DOMException)?.name;
        setStatus(name === 'NotAllowedError' ? 'denied' : 'error');
        return;
      }
      if (cancelled) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }

      const detector = new globalWithDetector.BarcodeDetector({ formats: ['qr_code'] });
      setStatus('scanning');

      const tick = async () => {
        if (cancelled || !videoRef.current) return;
        try {
          const results = await detector.detect(videoRef.current);
          if (results.length > 0 && results[0].rawValue) {
            setScanned(results[0].rawValue);
            stop();
            return;
          }
        } catch {
          // Transient detection errors are ignored; the next frame retries.
        }
        rafRef.current = requestAnimationFrame(() => void tick());
      };
      void tick();
    }

    void start();

    return () => {
      cancelled = true;
      stop();
    };
  }, [stop]);

  return (
    <div className="space-y-3" data-testid="qr-scanner">
      {status === 'scanning' ? (
        <div className="overflow-hidden rounded-md border border-surface-border bg-black">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={videoRef} playsInline muted className="h-56 w-full object-cover" />
        </div>
      ) : null}

      {status === 'starting' ? <p className="text-sm text-content-muted">Starting the camera...</p> : null}

      {status === 'unsupported' ? (
        <Alert tone="warning" title="Scanning is not available in this browser." nextStep="Type the code shown on the shop display below." />
      ) : null}
      {status === 'denied' ? (
        <Alert tone="warning" title="Camera permission was denied." nextStep="Allow camera access, or type the code shown on the shop display." />
      ) : null}
      {status === 'error' ? (
        <Alert tone="warning" title="We could not start the camera." nextStep="Type the code shown on the shop display instead." />
      ) : null}

      <TextField
        label="Shop code"
        help="Paste or type the code exactly as shown on the shop display."
        value={manual}
        onChange={(event) => setManual(event.target.value)}
        name="qr-manual"
      />

      {scanned ? (
        <Alert tone="info" title="Code scanned" nextStep="Confirm to send it to the server for verification.">
          <p className="break-all font-mono text-xs">{scanned.slice(0, 60)}{scanned.length > 60 ? '...' : ''}</p>
        </Alert>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          onClick={() => {
            const payload = scanned ?? manual.trim();
            if (payload) onScan(payload);
          }}
          disabled={!scanned && manual.trim().length === 0}
        >
          Use this code
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}