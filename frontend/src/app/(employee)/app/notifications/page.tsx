'use client';

import { useState } from 'react';
import Link from 'next/link';
import { formatRelative, humanize } from '@/lib/format';
import {
  useCreatePushSubscription,
  useMarkAllRead,
  useMarkNotificationRead,
  useNotificationPreferences,
  useNotifications,
  useUpdateNotificationPreferences
} from '@/features/notifications/hooks';
import { Card, CardBody } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Tabs, TabPanel } from '@/components/ui/Tabs';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Switch } from '@/components/ui/Form';
import { Badge } from '@/components/ui/Badge';

/** Convert the base64url VAPID public key to the Uint8Array PushManager expects. */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}
export default function EmployeeNotificationsPage() {
  const [tab, setTab] = useState('all');
  const list = useNotifications(tab === 'unread' ? { is_read: false } : {});
  const prefs = useNotificationPreferences();
  const updatePrefs = useUpdateNotificationPreferences();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllRead();
  const createPush = useCreatePushSubscription();
  const [pushState, setPushState] = useState<
    'idle' | 'subscribed' | 'unsupported' | 'denied' | 'unconfigured' | 'failed'
  >('idle');

  async function enablePush() {
    if (typeof Notification === 'undefined' || !('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPushState('unsupported');
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      setPushState('denied');
      return;
    }
    // The public VAPID key is server signing material and has no documented read endpoint, so it
    // is supplied by build configuration. Without it the browser cannot create a subscription and
    // we say so rather than pretending push is enabled.
    const vapidPublicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
    if (!vapidPublicKey) {
      setPushState('unconfigured');
      return;
    }
    try {
      const registration = await navigator.serviceWorker.ready;
      const existing = await registration.pushManager.getSubscription();
      const subscription =
        existing ??
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidPublicKey) as unknown as BufferSource
        }));
      const json = subscription.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
        setPushState('failed');
        return;
      }
      await createPush.mutateAsync({
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
        user_agent: navigator.userAgent.slice(0, 200)
      });
      setPushState('subscribed');
    } catch {
      setPushState('failed');
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Notifications</h1>
          <p className="text-sm text-content-muted">Task, order, leave and complaint updates.</p>
        </div>
        <Button variant="secondary" size="sm" loading={markAll.isPending} onClick={() => markAll.mutate()}>
          Mark all read
        </Button>
      </div>

      <Tabs
        tabs={[
          { id: 'all', label: 'All' },
          { id: 'unread', label: 'Unread' }
        ]}
        activeId={tab}
        onChange={setTab}
        ariaLabel="Notification filters"
      />

      <TabPanel id={tab} activeId={tab}>
        {list.isLoading ? (
          <SkeletonList rows={5} />
        ) : list.error ? (
          <ProblemAlert error={list.error} onRetry={() => void list.refetch()} />
        ) : (list.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No notifications" hint="You are all caught up." />
        ) : (
          <ul className="space-y-2">
            {list.data?.items.map((item) => (
              <li key={item.id}>
                <Card className={item.is_read ? 'opacity-80' : ''}>
                  <CardBody className="space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-semibold">{item.title}</p>
                      {!item.is_read ? <Badge tone="primary">New</Badge> : null}
                    </div>
                    <p className="text-sm text-content-muted">{item.body}</p>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-content-muted">
                      <span>{humanize(item.event_type)}</span>
                      <span>{formatRelative(item.created_at)}</span>
                      {item.deep_link ? (
                        <Link href={item.deep_link} className="text-primary underline">
                          Open
                        </Link>
                      ) : null}
                      {!item.is_read ? (
                        <button
                          type="button"
                          className="text-primary underline"
                          onClick={() => markRead.mutate(item.id)}
                        >
                          Mark read
                        </button>
                      ) : null}
                    </div>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </TabPanel>

      <Card>
        <CardBody className="space-y-3">
          <h2 className="text-base font-semibold">Preferences</h2>
          {prefs.isLoading ? (
            <SkeletonList rows={2} />
          ) : prefs.error ? (
            <ProblemAlert error={prefs.error} onRetry={() => void prefs.refetch()} />
          ) : (prefs.data?.items.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No configurable preferences.</p>
          ) : (
            <ul className="space-y-3">
              {prefs.data?.items.map((preference) => (
                <li key={`${preference.event_type}-${preference.channel}`}>
                  <Switch
                    label={`${humanize(preference.event_type)} - ${humanize(preference.channel)}`}
                    checked={preference.is_enabled}
                    disabled={!preference.can_disable || updatePrefs.isPending}
                    onChange={(next) =>
                      updatePrefs.mutate([{ event_type: preference.event_type, channel: preference.channel, is_enabled: next }])
                    }
                  />
                </li>
              ))}
            </ul>
          )}

          <div className="border-t border-surface-border pt-3">
            <p className="text-sm font-medium">Browser notifications</p>
            <p className="text-xs text-content-muted">
              Push is requested only after you opt in, never on first load.
            </p>
            <div className="mt-2">
              <Button variant="secondary" size="sm" onClick={() => void enablePush()} disabled={pushState === 'subscribed'}>
                {pushState === 'subscribed' ? 'Push enabled' : 'Enable browser notifications'}
              </Button>
            </div>
            {pushState === 'unsupported' ? <p className="mt-1 text-xs text-warning">This browser does not support push notifications.</p> : null}
            {pushState === 'denied' ? <p className="mt-1 text-xs text-warning">Notification permission was denied. Enable it in your browser settings to receive push.</p> : null}
            {pushState === 'unconfigured' ? (
              <p className="mt-1 text-xs text-warning">
                In-app notifications are on. Browser push needs a server push key, which has not been configured for this
                deployment yet.
              </p>
            ) : null}
            {pushState === 'failed' ? <p className="mt-1 text-xs text-danger">We could not register this device for push. Please try again.</p> : null}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}