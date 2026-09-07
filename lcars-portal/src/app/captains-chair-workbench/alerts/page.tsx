'use client';

/**
 * wb-native Push Alerts sub-page (Captain's Chair). Rebuild of the legacy
 * `(app)/alerts` page — same data hooks (`useAlerts`, `@/lib/notifications`),
 * wb-* markup instead of LCARS chrome. The legacy route now redirects here.
 *
 * Severity → state-tone mapping now shared via departments.ts's
 * alertSeverityToTone (2026-08-29, Severity-Vocab-Canonicalization-Plan) —
 * this page previously kept its own copy of the same map that
 * captains-chair-workbench/page.tsx also duplicated.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { WorkbenchShell } from '@/components/ui';
import { useAlerts } from '@/lib/useAlerts';
import { ALERT_KIND_LABEL, type AlertSeverity, type MobileAlert } from '@/lib/alerts';
import {
  notificationPermission,
  requestNotificationPermission,
  notifyEnabled,
  setNotifyEnabled,
} from '@/lib/notifications';
import { stateToneClasses, alertSeverityToTone } from '@/lib/departments';

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: 'Critical',
  high: 'High',
  warning: 'Notice',
};

function AlertCard({ alert }: { alert: MobileAlert }) {
  const c = stateToneClasses(alertSeverityToTone(alert.severity));
  return (
    <Link
      href={alert.href}
      className={`block rounded-lg border ${c.border} bg-wb-surface p-4 transition-colors hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${c.dot} ${alert.severity === 'critical' ? 'animate-pulse' : ''}`}
          aria-hidden
        />
        <span className={`text-[10px] font-bold uppercase tracking-[0.2em] ${c.text}`}>
          {SEVERITY_LABEL[alert.severity]}
        </span>
        <span className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">
          · {ALERT_KIND_LABEL[alert.kind]}
        </span>
      </div>
      <p className="mt-1.5 text-sm font-semibold leading-snug text-wb-ink">{alert.title}</p>
      <p className="mt-1 text-xs leading-relaxed text-wb-ink2">{alert.detail}</p>
      <p className="mt-2 border-t border-wb-line pt-2 text-xs italic text-wb-ink2">
        Why now: {alert.why}
      </p>
    </Link>
  );
}

function NotificationControl() {
  const [perm, setPerm] = useState<string>('default');
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    setPerm(notificationPermission());
    setEnabled(notifyEnabled());
  }, []);

  async function enable() {
    const result = await requestNotificationPermission();
    setPerm(result);
    setEnabled(result === 'granted');
  }
  function toggle() {
    const next = !enabled;
    setNotifyEnabled(next);
    setEnabled(next);
  }

  if (perm === 'unsupported') {
    return (
      <div className="rounded-lg border border-wb-line bg-wb-bg p-3 text-xs text-wb-ink2">
        Web notifications aren&apos;t supported here. Install to the Home Screen (Share → Add to Home Screen) on iOS 16.4+ to enable banner alerts.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-wb-line bg-wb-bg p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-wb-ink">Push notifications</p>
          <p className="text-[11px] text-wb-ink2">
            {perm === 'granted'
              ? enabled
                ? 'On — banners for critical & high alerts only.'
                : 'Permission granted — currently muted.'
              : 'Get a banner only when something genuinely needs you.'}
          </p>
        </div>
        {perm === 'granted' ? (
          <button
            onClick={toggle}
            className={`rounded-md border px-3 py-1.5 text-xs font-bold uppercase tracking-[0.15em] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
              enabled
                ? `${stateToneClasses('ok').border} ${stateToneClasses('ok').bg} ${stateToneClasses('ok').text}`
                : 'border-wb-line text-wb-ink2'
            }`}
          >
            {enabled ? 'On' : 'Off'}
          </button>
        ) : (
          <button
            onClick={enable}
            className="rounded-md bg-wb-sage-deep px-3 py-1.5 text-xs font-bold uppercase tracking-[0.15em] text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            Enable
          </button>
        )}
      </div>
    </div>
  );
}

export default function CaptainsChairAlertsPage() {
  // Display-only here; the always-mounted command bar owns notification firing.
  const { alerts, isLoading, lastUpdated, refresh } = useAlerts({ enableNotifications: false });

  const right = (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-wb-ink2">
        {lastUpdated
          ? `Updated ${lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })}`
          : ''}
      </span>
      <button
        onClick={refresh}
        className="rounded-md border border-wb-line px-2.5 py-1 text-[12px] text-wb-ink2 transition hover:bg-wb-line focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep"
      >
        ↻ Refresh
      </button>
    </div>
  );

  return (
    <WorkbenchShell wide
      title="Push Alerts"
      eyebrow="Captain's Chair"
      tagline="USS TJR · Push Alerts · gated: decision · escalation · blocked · review · wellness — nothing surfaces here unless it genuinely needs you."
      back={{ href: '/captains-chair-workbench', label: "Captain's Chair" }}
      right={right}
    >
      <div className="flex flex-col gap-4">
        <h1 className="font-serif text-2xl text-wb-ink">What needs you</h1>

        <NotificationControl />

        {isLoading ? (
          <p className="text-sm italic text-wb-ink2">Checking…</p>
        ) : alerts.length === 0 ? (
          <div className={`rounded-lg border ${stateToneClasses('ok').border} ${stateToneClasses('ok').bg} p-6 text-center`}>
            <p className={`font-serif text-lg font-bold ${stateToneClasses('ok').text}`}>All clear</p>
            <p className="mt-1 text-sm text-wb-ink2">
              Nothing needs your decision, nothing has escalated, nothing is blocked. You&apos;ll only see an alert here when it genuinely matters.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {alerts.map((a) => (
              <AlertCard key={a.id} alert={a} />
            ))}
          </div>
        )}
      </div>
    </WorkbenchShell>
  );
}
