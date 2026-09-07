'use client';

// INTELLIGENCE (Command-Experience vNext, Phase 2, mission §9.3) —
// consumes the one canonical intelligence headline (commandState.ts's
// deriveIntelligenceHeadline()) rather than independently curating a Top
// OSINT Signal / Top Health Signal / confidence count on this page.
// Technical and Health OSINT remain specialised workbenches — this panel
// only shows already-interpreted material, with a drill-down link to the
// full briefing.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { stateToneClasses } from '@/lib/departments';
import type { IntelligenceHeadlineResult } from '@/lib/commandState';

export function Intelligence({ headline, loading }: { headline: IntelligenceHeadlineResult; loading: boolean }) {
  if (loading) {
    return (
      <WorkbenchPanel title="Intelligence">
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      </WorkbenchPanel>
    );
  }

  const tone = headline.unknown ? 'unknown' : headline.headline === 'NO MATERIAL CHANGE' ? 'ok' : headline.headline === 'ELEVATED EXTERNAL CONDITIONS' ? 'crit' : 'warn';
  const c = stateToneClasses(tone);

  return (
    <WorkbenchPanel title="Intelligence" eyebrow="Already interpreted, not raw feeds">
      <p className={`text-sm font-semibold ${c.text}`}>{headline.headline}</p>
      <p className="mt-1 text-sm text-wb-ink/80">{headline.detail}</p>
      <Link href="/captains-brief-workbench" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
        Open briefing →
      </Link>
    </WorkbenchPanel>
  );
}
