// THE MASTER LIST. This array is the single source of truth for what
// counts as a "live workbench" in this platform — both the hub tile grid
// (workbenches/page.tsx) and WorkbenchShell's persistent switcher (UX
// review, 2026-08) render directly from it, so the two can't drift the way
// two independently-maintained arrays eventually do (exactly what happened
// to the Content Workbench tile description, which kept describing a
// "Captain approval ... in Decide" step after that step was removed —
// fixed here, not just relocated). Mirrored in docs/LIVE-WORKBENCHES.md
// for humans who won't open this file; that doc is generated from here,
// never hand-edited.
//
// If a route isn't in this list, it is legacy, deprecated, experimental,
// or intentionally zero-nav (contextual-entry pages like /investigate,
// /decide, /ask — see each page's own header comment for why) — not an
// accidental gap to silently patch. A page's absence here should always be
// a deliberate, commented decision on the page itself (see
// comms-workbench's deletion, 2026-08-29, for the pattern of removing a
// page outright once it's confirmed superseded rather than leaving it to
// rot half-reachable).

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
  {
    href: '/self-improvement-findings',
    title: 'Self-Improvement Findings',
    description: 'Review and decide on findings the platform has proposed about itself — approve, reject, or request more evidence.',
  },
];
