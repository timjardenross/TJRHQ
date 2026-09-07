'use client';

// Captain's Log (Human Systems) disabled for now (Captain directive,
// 2026-08-10). Recovery Pulse (via the Telegram XO bot) now drives Human
// Systems / Health workbench stats exclusively. This page previously wrote
// captains_log_entries directly from the browser client — that write path
// is disabled here, not deleted. Kept as a reachable page (rather than
// removed or redirected) in case it's bookmarked or linked elsewhere — it
// now only explains the pause. The link that pointed here (RecoveryView)
// has also been removed.

import { WorkbenchShell, Card } from '@/components/ui';

export default function CaptainsLogPage() {
  return (
    <WorkbenchShell wide
      title="Captain's Log"
      eyebrow="Recovery & Capacity"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench?domain=recovery', label: 'Recovery' }}
    >
      <Card title="Captain's Log disabled for now">
        <p className="text-sm leading-relaxed text-wb-ink2">
          Manual Captain&rsquo;s Log entry is disabled for now. Recovery Pulse (via the Telegram XO bot)
          is the Captain&rsquo;s single source for Human Systems capacity and stats at this time — this
          form no longer accepts new entries.
        </p>
      </Card>
    </WorkbenchShell>
  );
}
