'use client';

import Link from 'next/link';
import { useCommandCentre } from '@/lib/useCommandCentre';
import { useROSData } from '@/lib/useROSData';
import { useAlerts } from '@/lib/useAlerts';
import type { RecoveryPostureBand } from '@/lib/types';
import { ExecutiveSummary } from './ExecutiveSummary';

/**
 * MobileOperatingPicture — the iPhone-first daily operating picture (WP2).
 *
 * Reuse-first: composes the EXISTING hooks — useCommandCentre (recommended
 * action, ship status), useROSData (recovery posture), and the gated alerts
 * engine (decisions / escalations) — into a single readable card stack. No new
 * data sources. Renders cleanly above the existing desktop Captain's Chair grid.
 */

// 2026-08-10: was on raw department classes (text-medical/border-operations/
// etc) — REST rendered blue (the Medical department's identity colour) here
// while ROSPanels, right above this component on desktop and directly above
// it in the DOM on mobile, rendered REST as navy (department tones were
// deliberately collapsed to one accent, see ROSPanels.tsx's own note) — the
// same posture read as two different colours on the same page. Both now use
// the genuinely-semantic state-tone system (state-ok/warn/crit/unknown, see
// departments.ts's stateToneClasses) so REST reads the same alarming red
// everywhere.
const POSTURE_TONE: Record<RecoveryPostureBand, { text: string; border: string; bg: string; label: string }> = {
  STRONG: { text: 'text-state-ok', border: 'border-state-ok', bg: 'bg-state-ok/15', label: 'High' },
  STABLE: { text: 'text-state-ok', border: 'border-state-ok', bg: 'bg-state-ok/15', label: 'Moderate' },
  FRAGILE: { text: 'text-state-warn', border: 'border-state-warn', bg: 'bg-state-warn/15', label: 'Low' },
  REST: { text: 'text-state-crit', border: 'border-state-crit', bg: 'bg-state-crit/15', label: 'Rest priority' },
  UNKNOWN: { text: 'text-state-unknown', border: 'border-state-unknown', bg: 'bg-state-unknown/15', label: 'Unknown' },
};

export function MobileOperatingPicture() {
  const cc = useCommandCentre();
  const { posture } = useROSData();
  const { alerts } = useAlerts({ enableNotifications: false });

  const band: RecoveryPostureBand = posture.posture ?? 'UNKNOWN';
  const p = POSTURE_TONE[band];

  const decisionAlerts = alerts.filter((a) => a.kind === 'decision' || a.kind === 'eng_review');
  // 2026-08-10: alerts.ts synthesizes 'wellness-capacity-critical' straight
  // from posture === 'REST' (same posture, same message) — the "Capacity /
  // posture" card just below already shows that. Keeping it here duplicated
  // the REST warning a 3rd/4th time (decision banner + Escalations list).
  // Genuinely distinct wellness alerts (e.g. 'wellness-pain-critical', a
  // real pain-trend signal, not a posture restatement) still surface.
  const escalations = alerts.filter((a) => a.kind === 'escalation' || (a.kind === 'wellness' && a.severity === 'critical' && a.id !== 'wellness-capacity-critical'));
  const blocked = alerts.filter((a) => a.kind === 'delivery_failure');

  return (
    <div className="flex flex-col gap-3 lg:hidden">
      {/* ── What needs my decision? banner ── */}
      <Link
        href="/captains-chair-workbench/alerts"
        className={[
          'block rounded-lg border p-4',
          decisionAlerts.length > 0 || escalations.length > 0
            ? 'border-operations/60 bg-operations/10'
            : 'border-status/40 bg-status/5',
        ].join(' ')}
      >
        <p className="text-[10px] uppercase tracking-[0.3em] text-wb-ink2">What needs my decision?</p>
        {decisionAlerts.length > 0 || escalations.length > 0 ? (
          <>
            <p className="mt-1 text-xl font-bold text-operations">
              {decisionAlerts.length + escalations.length} need{decisionAlerts.length + escalations.length === 1 ? 's' : ''} you
            </p>
            <p className="mt-0.5 text-sm text-wb-ink/85">
              {(decisionAlerts[0] ?? escalations[0]).title}
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-[0.15em] text-operations">Open alerts →</p>
          </>
        ) : (
          <p className="mt-1 text-xl font-bold text-status">Nothing right now</p>
        )}
      </Link>

      {/* ── Capacity / posture ── */}
      <div className={`rounded-lg border ${p.border} ${p.bg} p-4`}>
        <p className="text-[10px] uppercase tracking-[0.3em] text-wb-ink2">Today’s capacity</p>
        <div className="mt-1 flex items-baseline gap-2">
          <p className={`text-2xl font-bold ${p.text}`}>{p.label}</p>
          <span className={`text-xs font-semibold uppercase tracking-wide ${p.text}`}>{band}</span>
        </div>
        {/* posture.posture_message intentionally not repeated here — the
            Recovery Posture panel above (ROSPanels.tsx, same page, mobile
            DOM order puts it right before this) already shows it; this
            card's job is just the at-a-glance band + label. */}
        <div className="mt-2 flex gap-2">
          <Link href="/human-systems-workbench/recovery-brief" className="flex-1 rounded-lg border border-medical/40 bg-medical/5 py-2 text-center text-[10px] uppercase tracking-[0.15em] text-medical">
            Recovery brief
          </Link>
          <Link href="/capture-workbench" className="flex-1 rounded-lg border border-engineering/40 bg-engineering/5 py-2 text-center text-[10px] uppercase tracking-[0.15em] text-engineering">
            Quick capture
          </Link>
        </div>
      </div>

      {/* ── Top priority + ship status (MSN-0303's ratified "headline + supporting tiles" duplicate) ── */}
      <ExecutiveSummary
        recommendation={cc.recommendedAction}
        recommendationTitle="Top priority"
        shipStatus={cc.shipStatus}
        statusTitle="Mission state · readiness"
        compact
      />

      {/* ── Escalations ── */}
      {escalations.length > 0 && (
        <div className="rounded-lg border border-operations/40 bg-operations/10 p-4">
          <p className="mb-2 text-[10px] uppercase tracking-[0.3em] text-operations">Escalations</p>
          <ul className="flex flex-col gap-1.5">
            {escalations.slice(0, 3).map((e) => (
              <li key={e.id} className="text-sm text-wb-ink/85">• {e.title}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Blocked work ── */}
      {blocked.length > 0 && (
        <Link href="/captains-chair-workbench/engineering-queue" className="block rounded-lg border border-operations/40 bg-operations/5 p-4">
          <p className="text-[10px] uppercase tracking-[0.3em] text-operations">Blocked / failed</p>
          <p className="mt-1 text-sm font-semibold text-operations">{blocked.length} item{blocked.length === 1 ? '' : 's'} need clearing</p>
          <p className="text-[11px] uppercase tracking-[0.15em] text-wb-ink2">Open engineering queue →</p>
        </Link>
      )}
    </div>
  );
}
