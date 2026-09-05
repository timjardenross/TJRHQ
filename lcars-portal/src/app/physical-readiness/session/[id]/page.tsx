'use client';

// Retired (Fleet Engineering Review 2026-08-11) — a near-total duplicate of
// a workbench sub-route that has since been deleted outright (2026-08-29,
// docs/UI-Layer-Debt-Handoff-2026-08-29.md-adjacent council item 2/5 —
// human-systems-workbench/page.tsx's own header comment confirms
// "readiness/* sub-routes... are all gone"). This page's link previously
// pointed at that now-deleted route — fixed 2026-09-05, alongside moving
// this notice out of the (app) route group with the rest of Physical
// Readiness's migration onto WorkbenchShell, to point at the real,
// currently-live history page instead.

import { WorkbenchShell } from '@/components/ui';
import Link from 'next/link';

export default function LegacyReadinessSessionPage() {
  return (
    <WorkbenchShell title="Session logging moved" eyebrow="Physical Readiness" tagline="USS TJR · Physical Readiness" back={{ href: '/physical-readiness', label: 'Physical Readiness' }}>
      <div className="rounded-lg border border-wb-line bg-white p-4">
        <p className="text-sm leading-relaxed text-wb-ink2">
          This legacy session-logging link no longer tracks sessions — see workout history instead.
        </p>
        <Link
          href="/physical-readiness/history"
          className="mt-3 inline-block rounded-lg border border-wb-line bg-white px-4 py-2 text-sm font-semibold text-wb-ink transition-colors hover:border-wb-sage-deep/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          Go to Workout History →
        </Link>
      </div>
    </WorkbenchShell>
  );
}
