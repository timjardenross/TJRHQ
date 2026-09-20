import Link from 'next/link';

// Retired 2026-08-11 (mobile/iPad responsive review, finding #3 — duplicate
// canonical routes), originally pointing at /captains-brief-workbench.
// That page itself retired 2026-09-19 (Briefs/Captain's Brief
// consolidation, Phase 5) and now redirects to /briefs — updated to point
// there directly rather than chain through an intermediate retired stub.
// No live canonical surface still links here — kept as an honest notice
// rather than deleted outright so an old bookmark doesn't 404.
export default function CaptainsBriefPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-wb-ink">
        Captain&apos;s Brief
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">
        This page has retired — Briefs is now the canonical briefing Workbench.{' '}
        <Link href="/briefs" className="text-wb-sage-deep underline hover:no-underline">
          Go to Briefs →
        </Link>
      </p>
    </div>
  );
}
