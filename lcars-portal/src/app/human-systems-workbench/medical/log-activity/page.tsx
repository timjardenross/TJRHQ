'use client';

// Manual capture retirement (Captain directive, 2026-08-10 — see
// .claude/skills/bot-reviews/fixes-2026-08-09/manual-capture-retirement.md):
// Recovery Pulse (via the Telegram XO bot) is now the platform's only
// manual health-data capture mechanism. This page previously let the
// Captain manually log an activity (writing `activity_logs` via
// /api/human-systems/activity) — that form is retired here. The route it
// posted to still exists (other, non-manual callers may rely on it) but
// this UI no longer offers a way to create new entries. Kept as a reachable
// page (rather than deleted or redirected) in case it's bookmarked or
// linked elsewhere — it now only explains the retirement.

import { WorkbenchShell, Card } from '@/components/ui';

export default function LogActivityPage() {
  return (
    <WorkbenchShell
      title="Log Activity"
      eyebrow="Health Tracking"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}
    >
      <Card title="Manual activity logging retired">
        <p className="text-sm leading-relaxed text-wb-ink2">
          Manual activity entry has been retired platform-wide. Recovery Pulse (via the Telegram XO
          bot) is now the Captain&rsquo;s single manual health-data capture mechanism — this form no
          longer accepts new entries.
        </p>
      </Card>
    </WorkbenchShell>
  );
}
