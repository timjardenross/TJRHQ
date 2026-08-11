import Link from 'next/link';
import { WorkbenchShell } from '@/components/ui';

// This page moved (2026-08 UX review). /workbenches is the one canonical
// landing page now — root '/' redirects there directly (see app/page.tsx).
// Retired here rather than deleted outright, matching the /decisions and
// /stage-progression precedent, so a bookmark or old link lands on an
// honest notice instead of a 404.
//
// This page's "needs attention" triage content (hot signals, pending
// briefs, Captain's Brief interrupts, stale sources) is retired with it,
// not migrated — GET /api/home/needs-attention is unchanged and still
// live if that view is worth rebuilding as part of /workbenches later.
export default function HomePage() {
  return (
    <WorkbenchShell title="Home" eyebrow="Moved" tagline="USS TJR">
      <p className="text-[13px] leading-relaxed text-wb-ink2">
        This page moved.{' '}
        <Link href="/workbenches" className="text-wb-sage-deep underline hover:no-underline">
          Go to Workbenches →
        </Link>
      </p>
    </WorkbenchShell>
  );
}
