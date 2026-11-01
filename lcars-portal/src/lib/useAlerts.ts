'use client';

/**
 * useAlerts — client hook for the Push Alerts surface (MSN-IOS-001 WP6).
 *
 * Polls the gated alert engine, exposes the current alert set, and fires a
 * Web Notification ONLY when a new critical/high alert id appears (so the
 * Captain is never spammed with the same alert twice). The last-notified
 * signature is persisted so a reload does not re-fire stale alerts.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { computeAlerts, type MobileAlert } from './alerts';
import { fireNotification, notifyEnabled, notificationPermission } from './notifications';

const LAST_NOTIFIED_KEY = 'lcars-alerts-last-notified';
const DEFAULT_POLL_MS = 120_000;
/** computeAlerts() fans out to 6 alert sources (each a Supabase-backed API
 *  route). Several useAlerts instances are usually mounted at once (the
 *  global nav badge plus the page's own list), so they share one in-flight
 *  or recent result instead of each polling separately. */
const SHARED_RESULT_MS = 30_000;
type AlertsResult = Awaited<ReturnType<typeof computeAlerts>>;
let shared: { at: number; promise: Promise<AlertsResult> } | null = null;

function sharedComputeAlerts(force: boolean): Promise<AlertsResult> {
  const now = Date.now();
  if (!force && shared && now - shared.at < SHARED_RESULT_MS) return shared.promise;
  const promise = computeAlerts();
  shared = { at: now, promise };
  promise.catch(() => {
    if (shared?.promise === promise) shared = null;
  });
  return promise;
}

export interface UseAlertsResult {
  alerts: MobileAlert[];
  isLoading: boolean;
  lastUpdated: Date | null;
  refresh: () => void;
  /** How many of the 6 underlying alert-source fetches failed on the last
   *  run — 0 in the common case. Lets a caller show a quiet "N sources
   *  unavailable" note without turning a real outage into a false alarm. */
  failedSources: number;
  totalSources: number;
}

export interface UseAlertsOptions {
  pollMs?: number;
  /** Only one mounted owner should fire notifications, to avoid duplicates. */
  enableNotifications?: boolean;
}

function loadNotified(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    return new Set(JSON.parse(window.localStorage.getItem(LAST_NOTIFIED_KEY) ?? '[]'));
  } catch {
    return new Set();
  }
}

function saveNotified(ids: Set<string>): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(LAST_NOTIFIED_KEY, JSON.stringify([...ids]));
}

export function useAlerts(options: UseAlertsOptions = {}): UseAlertsResult {
  const { pollMs = DEFAULT_POLL_MS, enableNotifications = false } = options;
  const [alerts, setAlerts] = useState<MobileAlert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [failedSources, setFailedSources] = useState(0);
  const [totalSources, setTotalSources] = useState(0);
  const notifiedRef = useRef<Set<string>>(loadNotified());

  const run = useCallback(async (force = false) => {
    const result = await sharedComputeAlerts(force);
    const next = result.alerts;
    setAlerts(next);
    setFailedSources(result.failedSources);
    setTotalSources(result.totalSources);
    setLastUpdated(new Date());
    setIsLoading(false);

    // Fire notifications only for newly-appeared critical/high alerts.
    if (enableNotifications && notifyEnabled() && notificationPermission() === 'granted') {
      const fresh = next.filter(
        (a) => (a.severity === 'critical' || a.severity === 'high') && !notifiedRef.current.has(a.id),
      );
      for (const a of fresh) {
        fireNotification(a.title, { body: a.why, tag: a.id, url: a.href });
        notifiedRef.current.add(a.id);
      }
      // Forget ids that are no longer active so they can re-fire if they recur.
      const activeIds = new Set(next.map((a) => a.id));
      notifiedRef.current = new Set([...notifiedRef.current].filter((id) => activeIds.has(id)));
      saveNotified(notifiedRef.current);
    }
  }, [enableNotifications]);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      run();
    };
    tick();
    // No polling while the tab is hidden — the visibilitychange handler
    // below refreshes as soon as it's shown again.
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') tick();
    }, pollMs);
    const onVisible = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [run, pollMs]);

  const refresh = useCallback(() => { void run(true); }, [run]);

  return { alerts, isLoading, lastUpdated, refresh, failedSources, totalSources };
}

/**
 * Nav-badge hook — also the single global owner that fires notifications,
 * since the command bar is always mounted across the app.
 */
export function useAlertCount(pollMs: number = DEFAULT_POLL_MS): number {
  const { alerts } = useAlerts({ pollMs, enableNotifications: true });
  return alerts.length;
}
