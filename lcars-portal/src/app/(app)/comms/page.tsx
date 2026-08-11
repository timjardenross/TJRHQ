import Link from 'next/link';

// Retired 2026-08-11 (Chief Engineer workbench-drift review). /content-workbench
// is a confirmed superset: its pipeline tab covers opportunity/draft/review/
// approved/ready_to_publish (same stages this page showed via advance()), and
// its portfolio tab (added via PR #16) covers published items — the one
// status this page's own flat list included that content-workbench's board
// doesn't. No content/capability lost.
//
// Kept as an honest "this page moved" notice rather than deleted outright,
// matching the /home and /captains-brief retirement precedent, so an old
// bookmark doesn't 404. Note: /comms-workbench (a different, still-live page)
// is NOT what this redirects to — that page was itself superseded by
// content-workbench and is kept alive only because its API routes are
// load-bearing for Content Workbench's approved->published step, not as a
// UI destination.
export default function CommsPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-lcars text-lg font-bold uppercase tracking-wider text-lcars-text">
        Communications Pipeline
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">
        This page moved.{' '}
        <Link href="/content-workbench" className="text-wb-sage-deep underline hover:no-underline">
          Go to Content Workbench →
        </Link>
      </p>
    </div>
  );
}
