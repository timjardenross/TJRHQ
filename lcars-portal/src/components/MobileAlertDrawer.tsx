'use client';

import { useEffect, useState } from 'react';
import { useAlerts } from '@/lib/useAlerts';
import { fetchDecisionsInbox, type DecisionItem } from '@/lib/decisions';
import { stateToneClasses, alertSeverityToTone } from '@/lib/departments';
import type { AlertSeverity } from '@/lib/alerts';

// 2026-08-29 (Severity-Vocab-Canonicalization-Plan): previously used
// department-identity colors (bg-operations/bg-command) to signal alert
// severity — the exact conflation stateToneClasses exists to prevent.
// Migrated onto the canonical alertSeverityToTone adapter.
function sevDot(severity: AlertSeverity): string {
  return stateToneClasses(alertSeverityToTone(severity)).dot;
}

function sevText(severity: AlertSeverity): string {
  return stateToneClasses(alertSeverityToTone(severity)).text;
}

export function MobileAlertDrawer() {
  const [open, setOpen] = useState(false);
  const { alerts, isLoading } = useAlerts();
  // 2026-08-29: was mockData's decisionsAwaitingApproval (static fake data
  // mixed into a real alert badge count with no visual distinction — the
  // trust bug a council review flagged). lib/decisions.ts's
  // fetchDecisionsInbox() is the real, already-governed decisions data
  // layer (Supabase-backed mission/engineering approvals) that the
  // /decisions page already uses; this was the only consumer of the mock
  // decisions array, so wiring in the real source removes the bug rather
  // than just labeling it.
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  const [decisionsLoading, setDecisionsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchDecisionsInbox()
      .then((data) => {
        if (!cancelled) setDecisions(data.actionable);
      })
      .finally(() => {
        if (!cancelled) setDecisionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const totalCount = alerts.length + decisions.length;

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
                      className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${sevDot(a.severity) || 'bg-lcars-muted'}`}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className={`text-[11px] font-bold uppercase ${sevText(a.severity) || 'text-lcars-text'}`}>
                        {a.title}
                      </p>
                      <p className="text-[10px] text-lcars-muted">{a.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Decisions awaiting approval — real data, see fetchDecisionsInbox() call above */}
          <section>
            <p className="mb-2 text-[10px] uppercase tracking-[0.2em] text-command">
              Decisions Awaiting Approval
              {!decisionsLoading && decisions.length > 0 && (
                <span className="ml-1 text-lcars-muted">({decisions.length})</span>
              )}
            </p>
            {decisionsLoading ? (
              <p className="text-sm text-lcars-muted">Loading…</p>
            ) : decisions.length === 0 ? (
              <p className="text-sm text-lcars-muted">No pending decisions.</p>
            ) : (
              <ol className="flex flex-col gap-2">
                {decisions.map((d) => (
                  <li
                    key={d.id}
                    className="flex gap-2 rounded-md border border-edge bg-panel-2/60 p-3"
                  >
                    <span className="shrink-0 font-mono text-xs font-bold text-command">
                      {d.code ?? d.source}
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
