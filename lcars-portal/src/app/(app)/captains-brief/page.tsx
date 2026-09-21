import { redirect } from 'next/navigation';

// Retired 2026-08-11 (mobile/iPad responsive review, finding #3 — duplicate
// canonical routes), originally pointing at /captains-brief-workbench.
// That page itself retired 2026-09-19 (Briefs/Captain's Brief
// consolidation, Phase 5) and now redirects to /briefs — updated to point
// there directly rather than chain through an intermediate retired stub.
// No live canonical surface still links here — kept as an honest notice
// rather than deleted outright so an old bookmark doesn't 404.
export default function CaptainsBriefPage() {
  redirect('/briefs');
}
