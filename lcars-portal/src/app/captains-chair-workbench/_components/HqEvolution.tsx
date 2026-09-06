'use client';

// HQ EVOLUTION (Command-Experience vNext, Phase 2, mission §9.6) — kept
// deliberately small: a count plus the single highest-value opportunity,
// never the Discover/Investigate/Improve/Learned surface, discovery queue,
// investigation workload, or learning backlog. Disappears entirely when
// there is nothing to consider (mission §4: "healthy systems should
// disappear").

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';

export function HqEvolution({ pendingCount, highestValueTitle }: { pendingCount: number | null; highestValueTitle: string | null }) {
  if (!pendingCount || pendingCount <= 0) return null;

  return (
    <WorkbenchPanel title="HQ Evolution">
      <p className="text-sm font-semibold text-wb-ink">
        {pendingCount} idea{pendingCount === 1 ? '' : 's'} worth considering
      </p>
      <p className="mt-1 text-sm text-wb-ink/80">
        {highestValueTitle ?? 'Evolution found a possible improvement overnight.'}
      </p>
      <Link href="/self-improvement-findings" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
        Review →
      </Link>
    </WorkbenchPanel>
  );
}
