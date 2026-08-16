'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAlerts } from '@/lib/useAlerts';
import { ALERT_KIND_LABEL, type AlertSeverity, type MobileAlert } from '@/lib/alerts';
import {
  notificationPermission,
  requestNotificationPermission,
  notifyEnabled,
  setNotifyEnabled,
} from '@/lib/notifications';

const SEVERITY_STYLE: Record<AlertSeverity, { border: string; text: string; dot: string; label: string }> = {
  critical: { border: 'border-operations/50', text: 'text-operations', dot: 'bg-operations', label: 'Critical' },
  high: { border: 'border-command/50', text: 'text-command', dot: 'bg-command', label: 'High' },
  warning: { border: 'border-medical/50', text: 'text-medical', dot: 'bg-medical', label: 'Notice' },
};

function AlertCard({ alert }: { alert: MobileAlert }) {
  const s = SEVERITY_STYLE[alert.severity];
  return (
    <Link href={alert.href} className={`block rounded-lcars border ${s.border} bg-panel/60 p-4 transition-colors hover:bg-panel-2/60`}>
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot} ${alert.severity === 'critical' ? 'animate-pulse' : ''}`} />
        <span className={`text-[10px] font-bold uppercase tracking-[0.2em] ${s.text}`}>{s.label}</span>
        <span className="text-[10px] uppercase tracking-[0.15em] text-lcars-muted">· {ALERT_KIND_LABEL[alert.kind]}</span>
      </div>
      <p className="mt-1.5 text-sm font-semibold text-lcars-text leading-snug">{alert.title}</p>
      <p className="mt-1 text-xs text-lcars-text/75 leading-relaxed">{alert.detail}</p>
      <p className="mt-2 border-t border-edge pt-2 text-xs italic text-lcars-muted">
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
      <div className="rounded-lcars border border-edge bg-panel/40 p-3 text-xs text-lcars-muted">
        Web notifications aren&apos;t supported here. Install to the Home Screen (Share → Add to Home Screen) on iOS 16.4+ to enable banner alerts.
      </div>
    );
  }

  return (
    <div className="rounded-lcars border border-edge bg-panel/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-lcars-text">Push notifications</p>
          <p className="text-[11px] text-lcars-muted">
            {perm === 'granted'
              ? enabled ? 'On — banners for critical & high alerts only.' : 'Permission granted — currently muted.'
              : 'Get a banner only when something genuinely needs you.'}
          </p>
        </div>
        {perm === 'granted' ? (
          <button
            onClick={toggle}
            className={`rounded-lcars border px-3 py-1.5 text-xs font-bold uppercase tracking-[0.15em] ${enabled ? 'border-status/50 bg-status/10 text-status' : 'border-edge text-lcars-muted'}`}
          >
            {enabled ? 'On' : 'Off'}
          </button>
        ) : (
          <button
            onClick={enable}
            className="rounded-lcars bg-operations px-3 py-1.5 text-xs font-bold uppercase tracking-[0.15em] text-space hover:opacity-80"
          >
            Enable
          </button>
        )}
      </div>
    </div>
  );
}

export default function AlertsPage() {
  // Display-only here; the always-mounted command bar owns notification firing.
  const { alerts, isLoading, lastUpdated, refresh } = useAlerts({ enableNotifications: false });

  return (
    <div className="mx-auto flex max-w-[640px] flex-col gap-4">
      <header className="flex items-end justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Push Alerts</p>
          <h1 className="font-sans text-2xl font-bold text-operations">What needs you</h1>
        </div>
        <button onClick={refresh} className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-lcars-text">
          Refresh
        </button>
      </header>

      <NotificationControl />

      {isLoading ? (
        <p className="text-sm text-lcars-muted italic">Checking…</p>
      ) : alerts.length === 0 ? (
        <div className="rounded-lcars border border-status/40 bg-status/5 p-6 text-center">
          <p className="font-sans text-lg font-bold text-status">All clear</p>
          <p className="mt-1 text-sm text-lcars-muted">
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

      <p className="text-center text-[10px] uppercase tracking-[0.15em] text-lcars-muted">
        {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })}` : ''}
        {' · gated: decision · escalation · blocked · review · wellness'}
      </p>
    </div>
  );
}
