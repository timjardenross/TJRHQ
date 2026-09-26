import Link from 'next/link';

// Retired 2026-09-19 (Mission 7 legacy-page sweep, §35). Confirmed zero
// live inbound links anywhere in the app. Traced all 4 sections before
// touching anything:
// - Recent Decisions (decisions table) -> superseded, same confirmation
//   as (app)/decisions's own retirement: live today via Captain's Chair's
//   Approvals Pending panel.
// - Captured Items (captured_items) -> superseded by Capture Workbench.
// - Friction Sources -> a client-derived view over the other three
//   (failed items / high-importance-unreviewed / failed events), not its
//   own data source — falls away once those are resolved.
// - Commander Events (commander_events) -> genuinely live (traced through
//   the backend: tools/supabase/client.py's log_commander_event, called
//   from exactly one live caller, platform-runtime/lib/build_learning_loop.py,
//   itself imported by research_learning_loop.py/comms_learning_loop.py/
//   mission_brief.py) but has NO Captain-facing view anywhere else in the
//   app. Not silently dropped — flagged below as an open gap rather than
//   quietly retired along with the other three, which were genuinely
//   superseded. Building a real "recent build/handoff activity" view
//   (Engineering Handoffs is the natural home given the payload shape —
//   decision_id/outcome_id/mission_title/status/handoff_path — not HQ
//   Evolution, an earlier wrong guess corrected in the mission record)
//   is real feature work, out of scope for a retirement pass; tracked in
//   Missions/Active/USS-TJR-MSN-0393-....md §5 rather than built here.
export default function OperationsPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-wb-ink">
        Operations
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">This page moved.</p>
      <ul className="mt-4 space-y-2 text-[13px] text-wb-ink2">
        <li>
          Decisions:{' '}
          <Link href="/captains-chair-workbench" className="text-wb-sage-deep underline hover:no-underline">
            Go to Captain&apos;s Chair →
          </Link>
        </li>
        <li>
          Captured items:{' '}
          <Link href="/capture-workbench" className="text-wb-sage-deep underline hover:no-underline">
            Go to Capture Workbench →
          </Link>
        </li>
      </ul>
      <p className="mt-4 text-[12px] text-wb-ink2">
        Recent build/handoff activity (this page&rsquo;s old &ldquo;Commander Events&rdquo; panel) has no
        dedicated view anywhere in HQ yet — a known, tracked gap, not something this page is still the
        only way to see.
      </p>
    </div>
  );
}
