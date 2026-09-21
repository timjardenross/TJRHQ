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
  Archive as ArchiveIcon,
  BookOpen,
  Activity,
  Lightbulb,
  GitPullRequest,
  ShoppingCart,
  Search as SearchIcon,
  History,
  Timer,
} from 'lucide-react';
import type { PrimaryActionContract } from '@/lib/designGovernance';

// Mission 7 §16 — the directory grid this drives (workbenches/page.tsx)
// used to render all ~19 tiles as one flat, unlabelled list; a Captain
// scanning for "the health one" or "where shopping list lives" had nothing
// but title text to go on, and it was a long single-column scroll on
// mobile. `group` gives that page real sections instead of inventing a new
// grouping model — it's the same command/triage-then-intelligence-then-
// pipelines-then-platform order the comment below already documented, just
// made renderable instead of implicit in array position.
export type WorkbenchGroup =
  | 'orient' | 'decide' | 'understand' | 'operate';

export const WORKBENCH_GROUP_META: Record<WorkbenchGroup, { label: string; hint: string }> = {
  orient: { label: 'Orient', hint: 'See what matters now and choose where to begin' },
  decide: { label: 'Decide & plan', hint: 'Turn priorities, questions, and commitments into a decision' },
  understand: { label: 'Understand', hint: 'Review intelligence, evidence, history, and personal capacity' },
  operate: { label: 'Operate HQ', hint: 'Capture, deliver, improve, and keep the platform healthy' },
};

export interface WorkbenchEntry {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  group: WorkbenchGroup;
}

export const PRIMARY_ACTIONS: Record<string, PrimaryActionContract> = {
  '/hub': { label: 'Open Captain’s Chair', href: '/captains-chair-workbench' },
  '/focus-workbench': { label: 'Start a focus session', href: '/focus-workbench' },
  '/captains-chair-workbench': { label: 'Review what needs you', href: '/captains-chair-workbench' },
  '/capture-workbench': { label: 'Capture an item', href: '/capture-workbench' },
  '/mission-workbench': { label: 'Review missions', href: '/mission-workbench' },
  '/weekly-review': { label: 'Start weekly review', href: '/weekly-review' },
  '/ready-room': { label: 'Choose what to do next', href: '/ready-room' },
  '/intelligence-workbench': { label: 'Review today’s intelligence', href: '/intelligence-workbench' },
  '/health-osint': { label: 'Review health evidence', href: '/health-osint' },
  '/emergency-alert-hub-workbench': { label: 'Check active alerts', href: '/emergency-alert-hub-workbench' },
  '/human-systems-workbench': { label: 'Check current capacity', href: '/human-systems-workbench' },
  '/physical-readiness': { label: 'Review movement record', href: '/physical-readiness' },
  '/shopping-list-workbench': { label: 'Review shopping list', href: '/shopping-list-workbench' },
  '/content-workbench': { label: 'Review content queue', href: '/content-workbench' },
  '/advisory-workbench': { label: 'Start a decision', href: '/advisory-workbench' },
  '/briefs': { label: 'Read latest brief', href: '/briefs' },
  '/knowledge-workbench': { label: 'Search command memory', href: '/knowledge-workbench' },
  '/search': { label: 'Search HQ', href: '/search' },
  '/timeline': { label: 'Review timeline', href: '/timeline' },
  '/agent-status-workbench': { label: 'Check HQ status', href: '/agent-status-workbench' },
  '/self-improvement-findings': { label: 'Review HQ evolution', href: '/self-improvement-findings' },
  '/engineering-handoffs': { label: 'Review engineering handoffs', href: '/engineering-handoffs' },
};

// Order below is deliberate, not alphabetical: command/triage surfaces
// first (what a Captain opens most), then domain intelligence, then work
// pipelines, then the archive, then platform-ops/meta last (2026-08-31 —
// switcher/hub order previously had no discernible grouping).
export const LIVE_WORKBENCHES: WorkbenchEntry[] = [
  {
    href: '/focus-workbench',
    title: 'Focus Workbench',
    description: 'ADHD-friendly execution — one next step, a clear time-box, and a calm way back when you get stuck.',
    icon: Timer,
    group: 'orient',
  },
  {
    href: '/hub',
    title: 'LifeOS Hub',
    description: 'Always-on glance view — situation strip, live alerts, calendar, reminders, and today\'s briefing. The front door.',
    icon: LayoutDashboard,
    group: 'orient',
  },
  {
    href: '/capture-workbench',
    title: 'Capture Workbench',
    description: 'Quick capture and inbox triage — everything that comes in via Telegram/Slack/API, live, in one place.',
    icon: Inbox,
    group: 'operate',
  },
  {
    href: '/captains-chair-workbench',
    title: "Captain's Chair",
    description: 'Operational dashboard — recovery posture, mission overview, alerts, and intelligence at a glance.',
    icon: Compass,
    group: 'orient',
  },
  {
    href: '/mission-workbench',
    title: 'Mission Workbench',
    description: 'Every active and completed mission — capacity-cost aware, filtered by what fits today\'s recovery posture.',
    icon: Rocket,
    group: 'decide',
  },
  {
    href: '/weekly-review',
    title: 'Weekly Review',
    description: 'One calm weekly pass across every workbench — what happened, what slipped, what needs attention, what is safe to ignore.',
    icon: BarChart3,
    group: 'decide',
  },
  {
    href: '/ready-room',
    title: 'Ready Room',
    description: 'Life admin and task decomposition in one place — what needs attention now, what is waiting on someone else, and a tiny first step for anything overwhelming.',
    icon: ListChecks,
    group: 'orient',
  },
  {
    href: '/intelligence-workbench',
    title: 'Technical OSINT Workbench',
    description: 'Cyber, infrastructure, and regulatory signal intelligence — source reliability, confidence scoring, and threat escalation.',
    icon: Radar,
    group: 'understand',
  },
  {
    href: '/health-osint',
    title: 'Health OSINT Workbench',
    description: 'Clinical trial and performance-research intelligence — source reliability, study confidence, and safety escalation.',
    icon: Heart,
    group: 'understand',
  },
  {
    href: '/emergency-alert-hub-workbench',
    title: 'Emergency Alerts',
    description: 'Official Australian emergency information, prioritised by what may require attention now.',
    icon: TriangleAlert,
    group: 'understand',
  },
  {
    href: '/human-systems-workbench',
    title: 'Human Systems',
    description: "Personal capacity intelligence — understand your current state, what's consuming capacity, what appears to help, and what may need to change.",
    icon: Users,
    group: 'understand',
  },
  {
    href: '/physical-readiness',
    title: 'Physical Readiness',
    description: 'Exercise library and workout history — a read-only record of what you\'ve done. Session generation and readiness check-in were retired (Captain directive, 2026-08-10/11); Recovery Pulse is the single source for capacity/stats now.',
    icon: Dumbbell,
    group: 'understand',
  },
  {
    href: '/shopping-list-workbench',
    title: 'Shopping List',
    description: 'Everything worth buying, wishlist to purchased — manually prioritised, filterable by category/status/recipient/occasion, with per-currency subtotals.',
    icon: ShoppingCart,
    group: 'decide',
  },
  {
    href: '/content-workbench',
    title: 'Content Workbench',
    description: 'Capture, research, draft, proof, and publish comms content end-to-end, plus a Portfolio of everything published — one QA-gated pipeline.',
    icon: FileText,
    group: 'operate',
  },
  {
    href: '/advisory-workbench',
    title: 'Advisory',
    description: 'Decision support — think through a question, challenge assumptions, explore perspectives, and learn from what happened.',
    icon: MessageSquare,
    group: 'decide',
  },
  {
    href: '/briefs',
    title: 'Briefs',
    description: 'The canonical briefing Workbench — the daily OSINT/world-news brief archive plus a merged cross-domain Domains picture, filterable and searchable.',
    icon: ArchiveIcon,
    group: 'understand',
  },
  {
    href: '/knowledge-workbench',
    title: 'Knowledge Workbench',
    description: 'Command memory — organisational decisions and the reasoning behind them, searchable in one place.',
    icon: BookOpen,
    group: 'understand',
  },
  {
    // Mission 7 §35/§16: relocated 2026-09-19 from app/(app)/search — a
    // real, maintained, cross-domain search with zero navigation path in
    // for months (confirmed zero live inbound links before this). See
    // app/search/page.tsx's own header comment for the full trace.
    href: '/search',
    title: 'Search',
    description: 'Cross-domain search — missions, Captain\'s Log, captures, and events, all from one search box.',
    icon: SearchIcon,
    group: 'understand',
  },
  {
    // Mission 7 §35/§16: relocated 2026-09-19 from app/(app)/timeline,
    // same pass and same reasoning as Search above (2 of Search's result
    // types link here).
    href: '/timeline',
    title: 'Timeline',
    description: 'One chronological feed across missions, health, log, events, and captures — filterable by source.',
    icon: History,
    group: 'understand',
  },
  {
    href: '/agent-status-workbench',
    title: 'HQ Status',
    description: 'Is HQ working properly? Interpreted platform health across capabilities, automations, sources, and machinery — not just a wall of job rows.',
    icon: Activity,
    group: 'operate',
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
    group: 'operate',
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
    group: 'operate',
  },
];
