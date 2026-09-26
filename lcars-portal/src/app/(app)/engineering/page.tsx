import Link from 'next/link';

// Retired 2026-09-19 (Mission 7 legacy-page sweep, §35). Confirmed zero
// live inbound links anywhere in the app. Traced all 4 sections to their
// real data sources before touching anything:
// - Build Request Inbox (build_request_inbox) -> superseded, live today
//   via Captain's Chair's Engineering Queue panel and lib/decide.ts's
//   governance flow (see (app)/decisions/page.tsx's own retirement
//   comment for the same confirmation).
// - Engineering Throughput (lib/engineeringMetrics.ts, itself already the
//   subject of a dedicated integrity fix — MSN-0351 removed a fabricated
//   composite "Cognitive Load Reduction" score it used to compute here)
//   and the Agent Performance / Batch Jobs panels all read agent_performance
//   and batch_jobs. A repo-wide search (Python and TypeScript both) found
//   zero live readers or writers of either table anywhere outside this
//   page and lib/engineeringMetrics.ts itself — no scheduler, bot, or API
//   route inserts into either. Weaker confidence than a table with a
//   confirmed dead writer (contrast commander_events, §3.6, which turned
//   out to still be genuinely live) — this is "found nothing after a real
//   search," not "confirmed retired" the way medical/captains-log were.
//   HQ Status (agent-status-workbench) is the current, live "is HQ's
//   automation working" surface either way.
export default function EngineeringPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-wb-ink">
        Engineering Deck
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">This page moved.</p>
      <ul className="mt-4 space-y-2 text-[13px] text-wb-ink2">
        <li>
          Build requests, throughput:{' '}
          <Link href="/captains-chair-workbench" className="text-wb-sage-deep underline hover:no-underline">
            Go to Captain&apos;s Chair →
          </Link>
        </li>
        <li>
          Is HQ&apos;s automation working:{' '}
          <Link href="/agent-status-workbench" className="text-wb-sage-deep underline hover:no-underline">
            Go to HQ Status →
          </Link>
        </li>
      </ul>
    </div>
  );
}
