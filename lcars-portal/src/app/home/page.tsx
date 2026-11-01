import { redirect } from 'next/navigation';

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
  redirect('/hub');
}
