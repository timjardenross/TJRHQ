import { redirect } from 'next/navigation';

// This page's real function — merging mission and engineering approvals
// into one queue — was planned as /decide (STARSHIP-REDESIGN.md §5) but
// that route was never built; the "moved" notice here pointed at a
// destination that doesn't exist. The closest real destination today is
// Captain's Chair, which already has both a mission Approvals Pending
// panel and an Engineering Queue panel (design-audit fleet-sweep
// follow-up, 2026-08-16).
export default function DecisionsPage() {
  redirect('/captains-chair-workbench');
}
