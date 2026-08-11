'use client';

// Readiness check-in removed (Captain directive, 2026-08-10/11). This is
// the legacy (app) twin of /human-systems-workbench/readiness/start, which
// was already retired the same way (commit f32ad53a) — this route was
// found still live and bypassing that decision (linked from
// MobileCommandBar.tsx and (app)/medical/page.tsx, both via the
// /physical-readiness landing page's "Start Today's Check-In" button,
// removed alongside this). Recovery Pulse (via the Telegram XO bot) is now
// the Captain's single source for Human Systems capacity and stats. Kept
// as a reachable page (rather than deleted) in case it's bookmarked or
// linked elsewhere — it now only explains the removal.

import { LCARSPanel } from '@/components/LCARSPanel';

export default function ReadinessCheckInPage() {
  return (
    <LCARSPanel title="Readiness check-in removed" accent="medical" eyebrow="Today's Readiness">
      <p className="text-sm leading-relaxed text-lcars-muted">
        Manual readiness check-in has been removed. Recovery Pulse (via the Telegram XO bot) is now
        the Captain&rsquo;s single source for Human Systems capacity and stats — this form no longer
        generates sessions.
      </p>
    </LCARSPanel>
  );
}
