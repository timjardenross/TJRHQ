'use client';

// HQ EVOLUTION (Command-Experience vNext, Phase 2, mission §9.6) — kept
// deliberately small: a count plus the single highest-value opportunity,
// never the Discover/Investigate/Improve/Learned surface, discovery queue,
// investigation workload, or learning backlog. Disappears entirely when
// there is nothing to consider (mission §4: "healthy systems should
// disappear").
//
// `reduced` (Mission 2, Capacity & Attention Engine, §17): these are
// discretionary "worth considering" opportunities, exactly what the
// capacity contract calls out for suppression under Amber ("suppress
// low-value opportunities") and Red ("avoid optional opportunities").
// Reduced mode never removes access to them -- mission §15's "recovery
// from suppression" requirement -- it collapses to one line with the same
// Review link, rather than hiding the section or dropping the count.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';

export function HqEvolution({
  pendingCount, highestValueTitle, reduced = false,
}: {
  pendingCount: number | null; highestValueTitle: string | null; reduced?: boolean;
}) {
  if (!pendingCount || pendingCount <= 0) return null;

  if (reduced) {
    return (
      <WorkbenchPanel title="HQ Evolution">
        <p className="text-sm text-wb-ink/80">
          {pendingCount} idea{pendingCount === 1 ? '' : 's'} parked while capacity is protected —{' '}
          <Link href="/self-improvement-findings" className="text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
            Review →
          </Link>
        </p>
      </WorkbenchPanel>
    );
  }

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
