import Link from 'next/link';

// Retired 2026-08-11 (mobile/iPad responsive review, finding #3 — duplicate
// canonical routes). /captains-brief-workbench is a confirmed strict
// superset: same single data source (GET /api/captain-brief), plus
// interrupt_now/insights rendering, a KPI dashboard, refresh/retry, and a
// Brief/Domains tab split this page never had. No live canonical surface
// still links here — matching the /home retirement precedent, kept as an
// honest notice rather than deleted outright so an old bookmark doesn't 404.
export default function CaptainsBriefPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-lcars text-lg font-bold uppercase tracking-wider text-lcars-text">
        Captain&apos;s Brief
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">
        This page moved.{' '}
        <Link href="/captains-brief-workbench" className="text-wb-sage-deep underline hover:no-underline">
          Go to Captain&apos;s Brief →
        </Link>
      </p>
    </div>
  );
}
