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
//
// `icon` added 2026-09-05 (Adaptive Themes + Home/Workbench Redesign
// mission, §13) — a component reference (lucide-react), not a string name,
// so a typo fails at compile time rather than silently rendering nothing.
//
// Sidebar/switcher review (2026-09-08): Mission Workbench, Capture
// Workbench, Captain's Brief, and Knowledge Workbench were live, linked-from
// multiple places pages that had simply never been added here — not a
// deliberate exclusion (none of their own header comments claim
// zero-nav/deprecated status; several explicitly say "Reachable from
// /workbenches"). Added below in priority order rather than left as a gap.

import type { LucideIcon } from 'lucide-react';
import {
  LayoutDashboard,
  Inbox,
  Compass,
  Rocket,
  BarChart3,
  ListChecks,
  Radar,
  Heart,
  TriangleAlert,
  Users,
  Dumbbell,
  FileText,
  MessageSquare,
  ScrollText,
  Archive as ArchiveIcon,
  BookOpen,
  Activity,
  Lightbulb,
  GitPullRequest,
  ShoppingCart,
} from 'lucide-react';

export interface WorkbenchEntry {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
}

// Order below is deliberate, not alphabetical: command/triage surfaces
// first (what a Captain opens most), then domain intelligence, then work
// pipelines, then the archive, then platform-ops/meta last (2026-08-31 —
// switcher/hub order previously had no discernible grouping).
export const LIVE_WORKBENCHES: WorkbenchEntry[] = [
  {
    href: '/hub',
    title: 'LifeOS Hub',
    description: 'Always-on glance view — situation strip, live alerts, calendar, reminders, and today\'s briefing. The front door.',
    icon: LayoutDashboard,
  },
  {
    href: '/capture-workbench',
    title: 'Capture Workbench',
    description: 'Quick capture and inbox triage — everything that comes in via Telegram/Slack/API, live, in one place.',
    icon: Inbox,
  },
  {
    href: '/captains-chair-workbench',
    title: "Captain's Chair",
    description: 'Operational dashboard — recovery posture, mission overview, alerts, and intelligence at a glance.',
    icon: Compass,
  },
  {
    href: '/mission-workbench',
    title: 'Mission Workbench',
    description: 'Every active and completed mission — capacity-cost aware, filtered by what fits today\'s recovery posture.',
    icon: Rocket,
  },
  {
    href: '/weekly-review',
    title: 'Weekly Review',
    description: 'One calm weekly pass across every workbench — what happened, what slipped, what needs attention, what is safe to ignore.',
    icon: BarChart3,
  },
  {
    href: '/ready-room',
    title: 'Ready Room',
    description: 'Life admin and task decomposition in one place — what needs attention now, what is waiting on someone else, and a tiny first step for anything overwhelming.',
    icon: ListChecks,
  },
  {
    href: '/intelligence-workbench',
    title: 'Technical OSINT Workbench',
    description: 'Cyber, infrastructure, and regulatory signal intelligence — source reliability, confidence scoring, and threat escalation.',
    icon: Radar,
  },
  {
    href: '/health-osint',
    title: 'Health OSINT Workbench',
    description: 'Clinical trial and performance-research intelligence — source reliability, study confidence, and safety escalation.',
    icon: Heart,
  },
  {
    href: '/emergency-alert-hub-workbench',
    title: 'Emergency Alerts',
    description: 'Official Australian emergency information, prioritised by what may require attention now.',
    icon: TriangleAlert,
  },
  {
    href: '/human-systems-workbench',
    title: 'Human Systems',
    description: "Personal capacity intelligence — understand your current state, what's consuming capacity, what appears to help, and what may need to change.",
    icon: Users,
  },
  {
    href: '/physical-readiness',
    title: 'Physical Readiness',
    description: 'Exercise library and workout history — a read-only record of what you\'ve done. Session generation and readiness check-in were retired (Captain directive, 2026-08-10/11); Recovery Pulse is the single source for capacity/stats now.',
    icon: Dumbbell,
  },
  {
    href: '/shopping-list-workbench',
    title: 'Shopping List',
    description: 'Everything worth buying, wishlist to purchased — manually prioritised, filterable by category/status/recipient/occasion, with per-currency subtotals.',
    icon: ShoppingCart,
  },
  {
    href: '/content-workbench',
    title: 'Content Workbench',
    description: 'Capture, research, draft, proof, and publish comms content end-to-end, plus a Portfolio of everything published — one QA-gated pipeline.',
    icon: FileText,
  },
  {
    href: '/advisory-workbench',
    title: 'Advisory',
    description: 'Decision support — think through a question, challenge assumptions, explore perspectives, and learn from what happened.',
    icon: MessageSquare,
  },
  {
    href: '/captains-brief-workbench',
    title: "Captain's Brief",
    description: 'The day\'s assembled briefing — KPIs, narrative brief, and domain breakdowns, refreshed on demand.',
    icon: ScrollText,
  },
  {
    href: '/briefs',
    title: 'Briefs',
    description: 'The intelligence brief archive - every synthesized OSINT/world-news brief, filterable by review/publish status.',
    icon: ArchiveIcon,
  },
  {
    href: '/knowledge-workbench',
    title: 'Knowledge Workbench',
    description: 'Command memory — organisational decisions and the reasoning behind them, searchable in one place.',
    icon: BookOpen,
  },
  {
    href: '/agent-status-workbench',
    title: 'HQ Status',
    description: 'Is HQ working properly? Interpreted platform health across capabilities, automations, sources, and machinery — not just a wall of job rows.',
    icon: Activity,
  },
  {
    // HQ Evolution (retitled from "Self-Improvement Findings" — the
    // existing evidence/policy/remediation engine is preserved underneath
    // and now covers overnight internal + external discovery too, not
    // just bounded remediation findings). Route kept for compatibility;
    // see docs/self-improvement/HQ-EVOLUTION.md.
    href: '/self-improvement-findings',
    title: 'HQ Evolution',
    description: 'Continuous improvement for TJR HQ — overnight discovery, research and investigation of new capabilities, open-source opportunities, cost reductions, reliability improvements and better ways for HQ to work.',
    icon: Lightbulb,
  },
  {
    // Added 2026-09-06 — previously this data (approved engineering
    // handoffs, live PR links, batch status) only ever fed Number One's
    // advisory work queue with no dedicated page anywhere in the platform;
    // the Captain had to leave for GitHub.com with nothing but a bare
    // handoff ID to find the right PR. Read-only: every action here opens
    // GitHub's own review view rather than approving/merging in-platform
    // (see engineering-handoffs/page.tsx's own header comment for why).
    // Named distinctly from /engineering-queue, a deliberate redirect stub
    // for a different, removed feature — see that route's own page.tsx.
    href: '/engineering-handoffs',
    title: 'Engineering Handoffs',
    description: 'Approved engineering handoffs awaiting triage, delivery, or your review — with a direct link to every draft PR so nothing sits waiting on a bare ID.',
    icon: GitPullRequest,
  },
];
