'use client';

// Retired (Fleet Engineering Review 2026-08-11) — this was a near-total
// duplicate of /human-systems-workbench/readiness/session/[id] (641-line
// diff between the two, same underlying physical_workout_sessions /
// physical_workout_exercise_logs tables, same session-logging flow, built
// on the older LCARSPanel/StatusBadge components instead of the current
// WorkbenchShell/Card/Badge/Input design system). Confirmed genuinely
// orphaned before retiring it: no in-app link anywhere reaches this route
// (grepped the whole lcars-portal/src tree) — the legacy (app)/physical-
// readiness landing page it lives under links only to its own /history
// and /library siblings, never into /session/[id]. Same treatment as
// /physical-readiness/start (commit f32ad53a): kept reachable rather than
// deleted, in case it's bookmarked, but the real flow now lives in the
// workbench.

import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';

export default function LegacyReadinessSessionPage() {
  return (
    <LCARSPanel title="Session logging moved" accent="medical" eyebrow="Physical Readiness">
      <p className="text-sm leading-relaxed text-lcars-muted">
        Workout session logging now lives in the Human Systems Workbench — this legacy page no
        longer tracks sessions.
      </p>
      <Link
        href="/human-systems-workbench/readiness/history"
        className="mt-3 inline-block rounded-lcars border border-edge bg-panel/50 px-4 py-2 text-sm font-semibold uppercase tracking-wider text-lcars-text hover:border-medical/60"
      >
        Go to Readiness History →
      </Link>
    </LCARSPanel>
  );
}
