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
// bookmark doesn't 404.
//
// 2026-08-29: /comms-workbench itself (also superseded by content-workbench)
// has now been deleted outright — it had zero real callers of its own UI
// (nav-orphaned since the same 2026-08 delisting this page describes) and
// nothing imported its components. The API routes it used to call
// (api/comms/[id]/advance, api/content/signals-to-opportunities) are still
// load-bearing for Content Workbench directly, independent of that page.
export default function CommsPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-lcars-text">
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
