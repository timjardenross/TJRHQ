'use client';

import Link from 'next/link';
import { useCommandCentre } from '@/lib/useCommandCentre';
import { useROSData } from '@/lib/useROSData';
import { useAlerts } from '@/lib/useAlerts';
import { toneClasses } from '@/lib/departments';
import type { RecoveryPostureBand } from '@/lib/types';

/**
 * MobileOperatingPicture — the iPhone-first daily operating picture (WP2).
 *
 * Reuse-first: composes the EXISTING hooks — useCommandCentre (recommended
 * action, ship status), useROSData (recovery posture), and the gated alerts
 * engine (decisions / escalations) — into a single readable card stack. No new
 * data sources. Renders cleanly above the existing desktop Captain's Chair grid.
 */

const POSTURE_TONE: Record<RecoveryPostureBand, { text: string; border: string; bg: string; label: string }> = {
  STRONG: { text: 'text-status', border: 'border-status', bg: 'bg-status/10', label: 'High' },
  STABLE: { text: 'text-command', border: 'border-command', bg: 'bg-command/10', label: 'Moderate' },
  FRAGILE: { text: 'text-operations', border: 'border-operations', bg: 'bg-operations/10', label: 'Low' },
  REST: { text: 'text-medical', border: 'border-medical', bg: 'bg-medical/10', label: 'Rest priority' },
  UNKNOWN: { text: 'text-lcars-muted', border: 'border-edge', bg: 'bg-edge/10', label: 'Unknown' },
};

export function MobileOperatingPicture() {
  const cc = useCommandCentre();
  const { posture } = useROSData();
  const { alerts } = useAlerts({ enableNotifications: false });

  const band: RecoveryPostureBand = posture.posture ?? 'UNKNOWN';
  const p = POSTURE_TONE[band];

  const decisionAlerts = alerts.filter((a) => a.kind === 'decision' || a.kind === 'eng_review');
  const escalations = alerts.filter((a) => a.kind === 'escalation' || (a.kind === 'wellness' && a.severity === 'critical'));
  const blocked = alerts.filter((a) => a.kind === 'delivery_failure');

  return (
    <div className="flex flex-col gap-3 lg:hidden">
      {/* ── What needs my decision? banner ── */}
      <Link
        href="/alerts"
        className={[
          'block rounded-lcars border p-4',
          decisionAlerts.length > 0 || escalations.length > 0
            ? 'border-operations/60 bg-operations/10'
            : 'border-status/40 bg-status/5',
        ].join(' ')}
      >
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">What needs my decision?</p>
        {decisionAlerts.length > 0 || escalations.length > 0 ? (
          <>
            <p className="mt-1 font-lcars text-xl font-bold text-operations">
              {decisionAlerts.length + escalations.length} need{decisionAlerts.length + escalations.length === 1 ? 's' : ''} you
            </p>
            <p className="mt-0.5 text-sm text-lcars-text/85">
              {(decisionAlerts[0] ?? escalations[0]).title}
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-[0.15em] text-operations">Open alerts →</p>
          </>
        ) : (
          <p className="mt-1 font-lcars text-xl font-bold text-status">Nothing right now</p>
        )}
      </Link>

      {/* ── Capacity / posture ── */}
      <div className={`rounded-lcars border ${p.border} ${p.bg} p-4`}>
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Today’s capacity</p>
        <div className="mt-1 flex items-baseline gap-2">
          <p className={`font-lcars text-2xl font-bold ${p.text}`}>{p.label}</p>
          <span className={`text-xs font-semibold uppercase tracking-wide ${p.text}`}>{band}</span>
        </div>
        {(posture.posture_message || posture.capacity_message) && (
          <p className="mt-1 text-sm text-lcars-text/80 leading-relaxed">
            {posture.posture_message || posture.capacity_message}
          </p>
        )}
        <div className="mt-2 flex gap-2">
          <Link href="/recovery-brief" className="flex-1 rounded-lcars border border-medical/40 bg-medical/5 py-2 text-center text-[10px] uppercase tracking-[0.15em] text-medical">
            Recovery brief
          </Link>
          <Link href="/capture" className="flex-1 rounded-lcars border border-engineering/40 bg-engineering/5 py-2 text-center text-[10px] uppercase tracking-[0.15em] text-engineering">
            Quick capture
          </Link>
        </div>
      </div>

      {/* ── Top priority (recommended action) ── */}
      {cc.recommendedAction && (
        <div className="rounded-lcars border border-command/40 bg-command/5 p-4">
          <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Top priority</p>
          <p className="mt-1 text-sm font-semibold text-command leading-snug">{cc.recommendedAction.action}</p>
          <p className="mt-1 text-[11px] text-lcars-muted">{cc.recommendedAction.sourceOfficer} · {cc.recommendedAction.confidence}</p>
        </div>
      )}

      {/* ── Escalations ── */}
      {escalations.length > 0 && (
        <div className="rounded-lcars border border-operations/40 bg-operations/10 p-4">
          <p className="mb-2 text-[10px] uppercase tracking-[0.3em] text-operations">Escalations</p>
          <ul className="flex flex-col gap-1.5">
            {escalations.slice(0, 3).map((e) => (
              <li key={e.id} className="text-sm text-lcars-text/85">• {e.title}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Current state — ship status (readiness signals) ── */}
      {cc.shipStatus.length > 0 && (
        <div className="rounded-lcars border border-edge bg-panel/60 p-4">
          <p className="mb-2 text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Mission state · readiness</p>
          <ul className="grid grid-cols-2 gap-2">
            {cc.shipStatus.slice(0, 6).map((s) => {
              const c = toneClasses(s.tone);
              return (
                <li key={s.key} className="rounded-md border border-edge bg-panel-2/60 p-2">
                  <div className="flex items-center gap-1.5">
                    <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
                    <span className="text-[10px] uppercase tracking-wide text-lcars-muted">{s.label}</span>
                  </div>
                  <p className={`mt-0.5 text-xs font-bold ${c.text}`}>{s.state}</p>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ── Blocked work ── */}
      {blocked.length > 0 && (
        <Link href="/engineering-queue" className="block rounded-lcars border border-operations/40 bg-operations/5 p-4">
          <p className="text-[10px] uppercase tracking-[0.3em] text-operations">Blocked / failed</p>
          <p className="mt-1 text-sm font-semibold text-operations">{blocked.length} item{blocked.length === 1 ? '' : 's'} need clearing</p>
          <p className="text-[11px] uppercase tracking-[0.15em] text-lcars-muted">Open engineering queue →</p>
        </Link>
      )}
    </div>
  );
}
