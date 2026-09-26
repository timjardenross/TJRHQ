import { redirect } from 'next/navigation';

// Retired 2026-09-19 (Briefs/Captain's Brief consolidation, Phase 5 — see
// BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md). Briefs' Domains tab
// (intelligence/brief/domains_view.py::assemble_domains_document(), shipped
// Phase 2-3) is now a confirmed-live, equivalent-or-superior merged
// cross-domain view over the same underlying assembly
// (core/platform/captain_brief_orchestrator.py) this page used to render
// standalone — the mission's own gate for retiring this page. No live
// canonical surface still links here (nav/registry entries updated in the
// same pass); kept as an honest notice rather than deleted outright so an
// old bookmark doesn't 404, matching the (app)/captains-brief retirement
// precedent (2026-08-11).
//
// The backend assembly this page used to call — /api/captain-brief,
// context-service's GET /brief/full, captain_brief_orchestrator.py, the
// Attention/Priority Engines — is NOT retired. Briefs' Domains tab depends
// on it directly; it is now shared platform infrastructure, not a
// single-UI backend.
export default function CaptainsBriefWorkbenchPage() {
  redirect('/briefs');
}
