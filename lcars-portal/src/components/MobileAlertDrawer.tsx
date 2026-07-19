'use client';

import { useState } from 'react';
import { useAlerts } from '@/lib/useAlerts';
import { decisionsAwaitingApproval } from '@/lib/mockData';
import type { AlertSeverity } from '@/lib/alerts';

const SEV_DOT: Record<AlertSeverity, string> = {
  critical: 'bg-operations',
  high:     'bg-operations',
  warning:  'bg-command',
};

const SEV_TEXT: Record<AlertSeverity, string> = {
  critical: 'text-operations',
  high:     'text-operations',
  warning:  'text-command',
};

export function MobileAlertDrawer() {
  const [open, setOpen] = useState(false);
  const { alerts, isLoading } = useAlerts();
  const totalCount = alerts.length + decisionsAwaitingApproval.length;

  return (
    <>
      {/* Trigger button — mobile only, hidden on xl+ where sidebar is visible */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="xl:hidden flex items-center gap-2 rounded-lcars border border-edge bg-panel/60 px-3 py-2 text-[11px] font-bold uppercase tracking-[0.2em] text-lcars-muted hover:border-command/60 hover:text-lcars-text transition-colors"
        aria-label={`Open alerts and decisions (${totalCount} items)`}
      >
        {totalCount > 0 && (
          <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-operations px-1 text-[10px] font-bold text-space">
            {totalCount > 9 ? '9+' : totalCount}
          </span>
        )}
        <span>Alerts &amp; Decisions</span>
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-space/70 backdrop-blur-sm xl:hidden"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Drawer — slides up from bottom */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Alerts and Decisions"
        aria-hidden={!open}
        className={[
          'fixed inset-x-0 bottom-0 z-50 max-h-[80dvh] overflow-y-auto rounded-t-2xl border-t border-edge bg-panel xl:hidden',
          'transition-transform duration-300 ease-out',
          open ? 'translate-y-0' : 'translate-y-full pointer-events-none',
        ].join(' ')}
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="mx-auto max-w-[640px] px-4 pt-4 pb-6">
          {/* Drag handle */}
          <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-edge" aria-hidden="true" />

          {/* Header */}
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.25em] text-lcars-muted">
              Alerts &amp; Decisions
            </h2>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-[11px] uppercase tracking-[0.15em] text-lcars-muted hover:text-lcars-text transition-colors"
              aria-label="Close alerts and decisions drawer"
            >
              ✕ Close
            </button>
          </div>

          {/* Active alerts — live via useAlerts() */}
          <section className="mb-5">
            <p className="mb-2 text-[10px] uppercase tracking-[0.2em] text-operations">
              Active Alerts
              {!isLoading && alerts.length > 0 && (
                <span className="ml-1 text-lcars-muted">({alerts.length})</span>
              )}
            </p>
            {isLoading ? (
              <p className="text-sm text-lcars-muted">Loading…</p>
            ) : alerts.length === 0 ? (
              <p className="text-sm text-lcars-muted">All systems nominal.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {alerts.map((a) => (
                  <li
                    key={a.id}
                    className="flex gap-2 rounded-md border border-edge bg-panel-2/60 p-3"
                  >
                    <span
                      className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${SEV_DOT[a.severity] ?? 'bg-lcars-muted'}`}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className={`text-[11px] font-bold uppercase ${SEV_TEXT[a.severity] ?? 'text-lcars-text'}`}>
                        {a.title}
                      </p>
                      <p className="text-[10px] text-lcars-muted">{a.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Decisions awaiting approval */}
          <section>
            <p className="mb-2 text-[10px] uppercase tracking-[0.2em] text-command">
              Decisions Awaiting Approval
              {decisionsAwaitingApproval.length > 0 && (
                <span className="ml-1 text-lcars-muted">({decisionsAwaitingApproval.length})</span>
              )}
            </p>
            {decisionsAwaitingApproval.length === 0 ? (
              <p className="text-sm text-lcars-muted">No pending decisions.</p>
            ) : (
              <ol className="flex flex-col gap-2">
                {decisionsAwaitingApproval.map((d) => (
                  <li
                    key={d.id}
                    className="flex gap-2 rounded-md border border-edge bg-panel-2/60 p-3"
                  >
                    <span className="shrink-0 font-mono text-xs font-bold text-command">
                      {d.id}
                    </span>
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold text-lcars-text">{d.title}</p>
                      <p className="text-[10px] text-lcars-muted">{d.detail}</p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
