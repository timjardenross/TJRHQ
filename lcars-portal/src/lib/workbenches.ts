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
    href: '/weekly-review',
    title: 'Weekly Review',
    description: 'One calm weekly pass across every workbench — what happened, what slipped, what needs attention, what is safe to ignore.',
  },
  {
    href: '/ready-room',
    title: 'Ready Room',
    description: 'Life admin and task decomposition in one place — what needs attention now, what is waiting on someone else, and a tiny first step for anything overwhelming.',
  },
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
  {
    href: '/briefs',
    title: 'Briefs',
    description: 'The intelligence brief archive - every synthesized brief across every domain, filterable by review/publish status.',
  },
  {
    href: '/agent-status-workbench',
    title: 'Agent & Job Status',
    description: 'Scheduler job health, agent run history, and failure triage across all automated platform tasks.',
  },
  {
    href: '/emergency-alert-hub-workbench',
    title: 'Emergency Alert Hub',
    description: 'Tier 1 official AU emergency alerts only — NSW/VIC/QLD/SA/ACT live feeds, jurisdiction and severity filters, per-source crawl health.',
  },
];
