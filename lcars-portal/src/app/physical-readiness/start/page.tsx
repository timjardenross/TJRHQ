'use client';

// Readiness check-in removed (Captain directive, 2026-08-10/11) — this
// notice moved from the (app) route group 2026-09-05 alongside the rest of
// Physical Readiness's migration onto WorkbenchShell. Recovery Pulse (via
// the Telegram XO bot) is the Captain's single source for Human Systems
// capacity and stats; this form no longer generates sessions.

import { WorkbenchShell } from '@/components/ui';

export default function ReadinessCheckInPage() {
  return (
    <WorkbenchShell title="Readiness check-in removed" eyebrow="Today's Readiness" tagline="USS TJR · Physical Readiness" back={{ href: '/physical-readiness', label: 'Physical Readiness' }}>
      <div className="rounded-lg border border-wb-line bg-white p-4">
        <p className="text-sm leading-relaxed text-wb-ink2">
          Manual readiness check-in has been removed. Recovery Pulse (via the Telegram XO bot) is now
          the Captain&rsquo;s single source for Human Systems capacity and stats — this form no longer
          generates sessions.
        </p>
      </div>
    </WorkbenchShell>
  );
}
