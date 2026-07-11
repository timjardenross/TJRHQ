import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';

// This page's real function - merging mission and engineering approvals
// into one queue - moved to /decide (STARSHIP-REDESIGN.md §5): one item
// at a time, plain question and reasoning, Approve/Hold/Undo, no ranked
// list. Retired here rather than deleted outright, matching the
// /stage-progression precedent, so a bookmark or old link lands on an
// honest notice instead of a 404 or a page slowly drifting out of date
// next to its replacement.

export default function DecisionsPage() {
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Decisions" accent="command" eyebrow="Moved">
        <p className="text-sm text-lcars-text/90 leading-relaxed">
          This page moved.{' '}
          <Link href="/decide" className="text-command underline underline-offset-2 hover:text-status-on">
            Go to Decide
          </Link>{' '}
          for mission and engineering approvals, one at a time.
        </p>
      </LCARSPanel>
    </div>
  );
}
