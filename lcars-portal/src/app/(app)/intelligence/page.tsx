import Link from 'next/link';

// Retired 2026-09-19 (Mission 7 legacy-page sweep, §35). This was the
// pre-"Three-Workbench Simplification" Intelligence Centre (MSN-0201
// rewire) — 6 tabs (Latest Brief, Signals, Themes, ORI Archive, Daily
// Briefs, Content) over /api/intelligence, which nothing else in the app
// calls. Confirmed zero live inbound links anywhere in the app.
//
// Traced each tab to its real successor via the tables /api/intelligence
// actually queried (not guessed from tab names alone):
// - Latest Brief / Daily Briefs / ORI Archive (intelligence_briefs,
//   captains_daily_briefs) -> Briefs, "the canonical briefing Workbench —
//   the daily OSINT/world-news brief archive" (its own description).
// - Signals / Themes (intelligence_events, intelligence_source_registry/
//   _health) -> Technical OSINT Workbench (/intelligence-workbench),
//   whose own header comment confirms it's the "Three-Workbench
//   Simplification, Phase 1" re-anchoring of this exact tab pair onto a
//   disposition-gated Today/Watching/Library model.
// - Content (content_signals, comms_content) -> Content Workbench
//   (/content-workbench), which owns the same two tables today (its own
//   header comment: "reuses comms_content/content_signals").
// All 3 successors confirmed live and current; nothing here has no home.
export default function IntelligencePage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-lcars-text">
        Intelligence
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">This page moved.</p>
      <ul className="mt-4 space-y-2 text-[13px] text-wb-ink2">
        <li>
          Latest Brief, Daily Briefs, ORI Archive:{' '}
          <Link href="/briefs" className="text-wb-sage-deep underline hover:no-underline">
            Go to Briefs →
          </Link>
        </li>
        <li>
          Signals, Themes:{' '}
          <Link href="/intelligence-workbench" className="text-wb-sage-deep underline hover:no-underline">
            Go to Technical OSINT Workbench →
          </Link>
        </li>
        <li>
          Content:{' '}
          <Link href="/content-workbench" className="text-wb-sage-deep underline hover:no-underline">
            Go to Content Workbench →
          </Link>
        </li>
      </ul>
    </div>
  );
}
