'use client';

/**
 * Web Notifications helper (MSN-IOS-001 WP6).
 *
 * MVP push model: locally-triggered Web Notifications fired by the running /
 * installed PWA when the gated alert set changes. On iOS 16.4+ an installed
 * (Add-to-Home-Screen) PWA can show these as real system banners.
 *
 * True server-initiated push for a *closed* app (VAPID + Web Push + a Supabase
 * edge function to send) is documented as the next-phase deliverable in
 * docs/MOBILE-MVP.md — it is intentionally out of MVP scope to avoid standing
 * up a parallel backend.
 */

const NOTIFY_PREF_KEY = 'lcars-alerts-notify-enabled';

export function notificationsSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window;
}

export function notificationPermission(): NotificationPermission | 'unsupported' {
  if (!notificationsSupported()) return 'unsupported';
  return Notification.permission;
}

export function notifyEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(NOTIFY_PREF_KEY) === 'true';
}

export function setNotifyEnabled(on: boolean): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(NOTIFY_PREF_KEY, on ? 'true' : 'false');
}

export async function requestNotificationPermission(): Promise<NotificationPermission | 'unsupported'> {
  if (!notificationsSupported()) return 'unsupported';
  try {
    const result = await Notification.requestPermission();
    if (result === 'granted') setNotifyEnabled(true);
    return result;
  } catch {
    return Notification.permission;
  }
}

export interface FireOptions {
  body?: string;
  tag?: string;
  url?: string;
}

/** Show a notification via the service worker when possible, else a plain one. */
export async function fireNotification(title: string, opts: FireOptions = {}): Promise<void> {
  if (!notificationsSupported() || Notification.permission !== 'granted') return;
  const options: NotificationOptions & { data?: unknown } = {
    body: opts.body,
    tag: opts.tag,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: opts.url ?? '/alerts' },
  };
  try {
    if ('serviceWorker' in navigator) {
      const reg = await navigator.serviceWorker.getRegistration();
      if (reg) {
        await reg.showNotification(title, options);
        return;
      }
    }
    new Notification(title, options);
  } catch {
    /* notification failures are non-fatal */
  }
}
