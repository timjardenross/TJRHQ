'use client';

// Readiness check-in removed (Captain directive, 2026-08-10). Recovery Pulse
// (via the Telegram XO bot) now drives Human Systems / Health workbench
// stats exclusively. This page previously generated a workout session from
// a manual check-in form (writing physical_readiness_checkins and
// physical_workout_sessions directly) — that flow is removed. Kept as a
// reachable page (rather than deleted) in case it's bookmarked or linked
// elsewhere — it now only explains the removal. The links that pointed here
// (RecoveryView, ReadinessView) have also been removed.

import { WorkbenchShell, Card } from '@/components/ui';

export default function ReadinessCheckInPage() {
  return (
    <WorkbenchShell
      title="Today's Readiness"
      eyebrow="Fitness Readiness"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench?domain=readiness', label: 'Readiness' }}
    >
      <Card title="Readiness check-in removed">
        <p className="text-sm leading-relaxed text-wb-ink2">
          Manual readiness check-in has been removed. Recovery Pulse (via the Telegram XO bot) is now
          the Captain&rsquo;s single source for Human Systems capacity and stats — this form no longer
          generates sessions.
        </p>
      </Card>
    </WorkbenchShell>
  );
}
