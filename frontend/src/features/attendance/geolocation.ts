'use client';

/**
 * One-shot geolocation capture for a single attendance event.
 *
 * There is NO continuous tracking and no background geolocation
 * (docs/07_UI_SPEC.md section 8, AGENTS.md section 9). The browser API is used only when the
 * server says the configured verification mode needs a location.
 */

export interface LocationFix {
  latitude: number;
  longitude: number;
  accuracy_meters: number;
  location_captured_at: string;
}

export type LocationFailureCode = 'LOCATION_UNAVAILABLE' | 'LOCATION_STALE' | 'PERMISSION_DENIED';

export class LocationError extends Error {
  readonly code: LocationFailureCode;
  constructor(code: LocationFailureCode, message: string) {
    super(message);
    this.name = 'LocationError';
    this.code = code;
  }
}

/** Ask whether the browser has already granted, denied or never asked for geolocation. */
export async function locationPermissionState(): Promise<'granted' | 'denied' | 'prompt' | 'unsupported'> {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) return 'unsupported';
  try {
    const permissions = navigator.permissions;
    if (!permissions?.query) return 'prompt';
    const status = await permissions.query({ name: 'geolocation' as PermissionName });
    return status.state as 'granted' | 'denied' | 'prompt';
  } catch {
    return 'prompt';
  }
}

export function getCurrentLocation(options: { timeoutMs?: number; maxAgeMs?: number } = {}): Promise<LocationFix> {
  const timeoutMs = options.timeoutMs ?? 15_000;

  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      reject(new LocationError('LOCATION_UNAVAILABLE', 'This device does not support location.'));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_meters: position.coords.accuracy,
          // The server validates freshness against attendance.location_max_age_seconds.
          location_captured_at: new Date(position.timestamp).toISOString()
        });
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          reject(new LocationError('PERMISSION_DENIED', 'Location permission was denied.'));
          return;
        }
        reject(new LocationError('LOCATION_UNAVAILABLE', 'We could not read your location.'));
      },
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: options.maxAgeMs ?? 0 }
    );
  });
}