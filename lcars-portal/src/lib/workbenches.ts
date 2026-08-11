// Canonical list of the live, hub-listed workbenches — single source of
// truth for both the hub tile grid (workbenches/page.tsx) and
// WorkbenchShell's persistent switcher (UX review, 2026-08), so the two
// can't drift the way two independently-maintained arrays eventually do
// (exactly what happened to the Content Workbench tile description, which
// kept describing a "Captain approval ... in Decide" step after that step
// was removed — fixed here, not just relocated).

export interface WorkbenchEntry {
  href: string;
  title: string;
  description: string;
}

export const LIVE_WORKBENCHES: WorkbenchEntry[] = [
  {
    href: '/captains-chair-workbench',
    title: "Captain's Chair",
    description: 'Operational dashboard — recovery posture, mission overview, alerts, and intelligence at a glance.',
  },
  {
    href: '/intelligence-workbench',
    title: 'Technical OSINT Workbench',
    description: 'Cyber, infrastructure, and regulatory signal intelligence — source reliability, confidence scoring, and threat escalation.',
  },
  {
    href: '/health-osint',
    title: 'Health OSINT Workbench',
    description: 'Clinical trial and performance-research intelligence — source reliability, study confidence, and safety escalation.',
  },
  {
    href: '/content-workbench',
    title: 'Content Workbench',
    description: 'Capture, research, draft, proof, and publish comms content end-to-end, plus a Portfolio of everything published — one QA-gated pipeline.',
  },
  {
    href: '/human-systems-workbench',
    title: 'Human Systems Workbench',
    description: 'Recovery posture, medical tracking, and physical readiness in one collection - live from the recovery-pulse signal.',
  },
  {
    href: '/advisory-workbench',
    title: 'Advisory Workbench',
    description: 'Consult officer advisors, convene the strategic Board, and hear distinguished perspectives - one advisory brain across surfaces.',
  },
];
