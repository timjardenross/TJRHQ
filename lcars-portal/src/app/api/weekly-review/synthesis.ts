/**
 * Weekly Review synthesis layer (2026-09-05 redesign).
 *
 * Pure, deterministic, rule-based — no LLM call, matching the same
 * discipline deriveSystemPosture()/computeStrategicPosture() already use
 * (Human Systems spec §35: "deterministic, no LLM"). Lives in its own
 * sibling file for the same reason those two do: route.ts files only
 * permit HTTP-method exports (see strategic-posture.ts's header comment).
 *
 * Takes the existing per-section Signal data (unchanged, still computed by
 * route.ts's reviewChair/reviewOsint/etc.) plus the prior week's stored
 * signal-count snapshot and today's StrategicPosture, and produces the
 * interpreted view model described in the mission brief. No new tables, no
 * new queries beyond what route.ts already runs — this is pure
 * interpretation of data that already exists.
 */

import type {
  CarryForwardItem,
  ChangeItem,
  DeltaGlyph,
  DomainSynthesis,
  LearnedItem,
  MatteredItem,
  Signal,
  WatchItem,
  WeekInReview,
  WeeklyReviewSynthesis,
  WorkbenchSection,
} from '@/lib/weeklyReview';
import type { StrategicPosture } from '@/app/human-systems-workbench/_components/types';

function findSection(sections: WorkbenchSection[], key: string): WorkbenchSection | undefined {
  return sections.find((s) => s.key === key);
}

function findSignal(sections: WorkbenchSection[], sectionKey: string, signalKey: string): Signal | undefined {
  return findSection(sections, sectionKey)?.signals.find((s) => s.key === signalKey);
}

/** Count of a signal, or null if the source couldn't be checked this run —
 * callers must handle null explicitly (never coerce to 0, per brief §29). */
function count(sections: WorkbenchSection[], sectionKey: string, signalKey: string): number | null {
  const s = findSignal(sections, sectionKey, signalKey);
  if (!s || s.unavailable) return null;
  return s.count;
}

// Signal-count map key format shared with route.ts's persistence — every
// countable (non-unavailable) signal across every section, flattened for a
// cheap week-over-week diff without needing a second staging table.
export function flattenSignalCounts(sections: WorkbenchSection[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const section of sections) {
    for (const s of section.signals) {
      if (s.unavailable) continue;
      out[`${section.key}:${s.key}`] = s.count;
    }
  }
  return out;
}

// Only these signals are material enough to lead "What Changed" with — a
// raw diff over all ~30 signals would just recreate the "wall of counts"
// problem the brief explicitly asks to solve (§7: "prioritise material
// changes over every metric that moved").
const MATERIAL_CHANGE_KEYS: { section: string; signal: string; label: string; goodDirection: 'down' | 'up' }[] = [
  { section: 'human-systems', signal: 'overload', label: 'Personal capacity', goodDirection: 'down' },
  { section: 'human-systems', signal: 'declined', label: 'Days trending down', goodDirection: 'down' },
  { section: 'osint', signal: 'escalated', label: 'Technical environment', goodDirection: 'down' },
  { section: 'health-osint', signal: 'flagged', label: 'Health safety signals', goodDirection: 'down' },
  { section: 'health-osint', signal: 'strong', label: 'Health evidence', goodDirection: 'up' },
  { section: 'agent-status', signal: 'repeated', label: 'Systems reliability', goodDirection: 'down' },
  { section: 'content', signal: 'blocked', label: 'Content', goodDirection: 'down' },
];

function buildWhatChanged(sections: WorkbenchSection[], prior: Record<string, number> | null): ChangeItem[] {
  return MATERIAL_CHANGE_KEYS.map(({ section, signal, label, goodDirection }) => {
    const key = `${section}:${signal}`;
    const current = count(sections, section, signal);
    if (current === null) {
      return { key, label, glyph: 'flat' as DeltaGlyph, detail: `${label} couldn't be checked this run.`, noHistory: false };
    }
    if (!prior || !(key in prior)) {
      return {
        key, label,
        glyph: current > 0 ? (goodDirection === 'down' ? 'warn' : 'ok') : 'flat',
        detail: current > 0 ? `${current} this week. No prior week to compare against yet.` : 'Nothing this week. No prior week to compare against yet.',
        noHistory: true,
      };
    }
    const priorCount = prior[key];
    const delta = current - priorCount;
    let glyph: DeltaGlyph;
    if (delta === 0) glyph = 'flat';
    else if (goodDirection === 'down') glyph = delta > 0 ? 'warn' : 'ok';
    else glyph = delta > 0 ? 'ok' : 'warn';
    const detail = delta === 0
      ? `Unchanged at ${current} (was ${priorCount} last week).`
      : `${current} this week versus ${priorCount} last week.`;
    return { key, label, glyph, detail, noHistory: false };
  });
}

function buildWhatMattered(sections: WorkbenchSection[]): MatteredItem[] {
  const items: MatteredItem[] = [];
  for (const section of sections) {
    for (const s of section.signals) {
      if (s.unavailable || s.count === 0) continue;
      if (s.tone !== 'crit' && s.tone !== 'warn') continue;
      items.push({
        key: `${section.key}:${s.key}`,
        title: `${section.title}: ${s.label}`,
        why: `${s.count} this week.`,
        tone: s.tone,
        href: section.href,
      });
    }
  }
  // Crit first, then warn; cap at 5 per brief §8 ("3-5 genuinely meaningful items").
  return items
    .sort((a, b) => (a.tone === b.tone ? 0 : a.tone === 'crit' ? -1 : 1))
    .slice(0, 5);
}

function buildLearned(sections: WorkbenchSection[], strategicMessage: string, hasStrategicSignal: boolean): LearnedItem[] {
  const learned: LearnedItem[] = [];

  if (hasStrategicSignal) {
    learned.push({
      key: 'recovery-trajectory',
      title: 'Recovery',
      lesson: strategicMessage,
    });
  }

  const highConf = count(sections, 'osint', 'high-confidence');
  const escalated = count(sections, 'osint', 'escalated');
  if (highConf !== null && escalated !== null && highConf > 0 && escalated === 0) {
    learned.push({
      key: 'osint-volume-vs-escalation',
      title: 'Intelligence',
      lesson: 'Higher technical signal volume this week did not translate into higher escalation risk — corroboration filtering appears to be doing its job, not just adding noise.',
    });
  }

  const blocked = count(sections, 'content', 'blocked');
  if (blocked !== null && blocked > 0) {
    learned.push({
      key: 'content-qa-gate',
      title: 'Content',
      lesson: `${blocked} item(s) were held at QA rather than published as-is — the gate caught something worth a second look before it went out.`,
    });
  }

  return learned.slice(0, 3);
}

function buildCarryForward(sections: WorkbenchSection[], posture: StrategicPosture): CarryForwardItem[] {
  const items: CarryForwardItem[] = [];

  if (posture === 'recover' || posture === 'protect') {
    items.push({
      key: 'protect-capacity',
      title: 'Recovery',
      detail: 'Recovery posture recommends protecting capacity into next week.',
      recommendation: 'Continue reduced commitments until posture improves.',
      href: '/human-systems-workbench',
    });
  }

  const contentBlockedSignal = findSignal(sections, 'content', 'blocked');
  if (contentBlockedSignal && !contentBlockedSignal.unavailable && contentBlockedSignal.count > 0) {
    for (const item of contentBlockedSignal.items.slice(0, 3)) {
      items.push({
        key: `content-blocked-${item.id}`,
        title: 'Content',
        detail: `"${item.title}" is blocked at QA.`,
        recommendation: 'Review and decide whether it still belongs in next week\'s plan.',
        signalItem: { ...item, sourceLabel: 'Content Workbench', signalLabel: contentBlockedSignal.label, tone: contentBlockedSignal.tone },
      });
    }
  }

  const readyToPublishSignal = findSignal(sections, 'content', 'ready');
  if (readyToPublishSignal && !readyToPublishSignal.unavailable && readyToPublishSignal.count > 0) {
    for (const item of readyToPublishSignal.items.slice(0, 3)) {
      items.push({
        key: `content-ready-${item.id}`,
        title: 'Content',
        detail: `"${item.title}" passed QA and is ready to schedule.`,
        recommendation: 'Decide a publish date.',
        signalItem: { ...item, sourceLabel: 'Content Workbench', signalLabel: readyToPublishSignal.label, tone: readyToPublishSignal.tone },
      });
    }
  }

  const repeated = findSignal(sections, 'agent-status', 'repeated');
  if (repeated && !repeated.unavailable && repeated.count > 0) {
    items.push({
      key: 'agent-repeated-failures',
      title: 'Systems',
      detail: `${repeated.count} job(s) failed repeatedly this week.`,
      recommendation: 'Investigate before next week.',
      href: '/agent-status-workbench',
    });
  }

  const escalated = findSignal(sections, 'osint', 'escalated');
  if (escalated && !escalated.unavailable && escalated.count > 0) {
    items.push({
      key: 'osint-escalated',
      title: 'Intelligence',
      detail: `${escalated.count} technical signal(s) crossed an escalation threshold.`,
      recommendation: 'Keep watch — no further action unless a new threshold is crossed.',
      href: '/intelligence-workbench',
    });
  }

  const decisions = findSignal(sections, 'chair', 'decisions');
  if (decisions && !decisions.unavailable && decisions.count > 0) {
    items.push({
      key: 'held-decisions',
      title: "Captain's Chair",
      detail: `${decisions.count} decision(s) remain on hold.`,
      recommendation: 'Resolve or explicitly re-hold.',
      href: '/captains-chair-workbench',
    });
  }

  return items;
}

function buildYouCanIgnore(sections: WorkbenchSection[]): string[] {
  const lines: string[] = [];

  const uncorroborated = count(sections, 'osint', 'uncorroborated');
  if (uncorroborated !== null && uncorroborated > 0) {
    lines.push(`${uncorroborated} lower-confidence technical signal(s) remain under automated monitoring — no action required unless one is escalated.`);
  }

  const appraisal = count(sections, 'health-osint', 'appraisal');
  const flagged = count(sections, 'health-osint', 'flagged');
  if (appraisal !== null && appraisal > 0) {
    const safetyLine = flagged === 0 ? ' No safety-flagged item is among them.' : '';
    lines.push(`${appraisal} health signal(s) remain queued for curation review.${safetyLine}`);
  }

  const staleAgents = count(sections, 'agent-status', 'stale');
  if (staleAgents !== null && staleAgents > 0) {
    lines.push(`${staleAgents} schedule(s) are running behind cadence but haven't failed — being watched automatically.`);
  }

  return lines;
}

function buildWatchNextWeek(sections: WorkbenchSection[], strategicMessage: string, hasStrategicSignal: boolean): WatchItem[] {
  const escalated = count(sections, 'osint', 'escalated');
  const items: WatchItem[] = [
    {
      key: 'technical-known-unknowns',
      label: 'Technical',
      detail: escalated === 0
        ? 'No escalation required this week, but coverage-gap ("Known Unknowns") tracking isn\'t wired into Weekly Review yet — treat automated monitoring as incomplete visibility, not confirmed safety.'
        : 'Coverage-gap ("Known Unknowns") tracking isn\'t wired into Weekly Review yet.',
      available: false,
    },
    {
      key: 'health-evidence-gaps',
      label: 'Health',
      detail: 'Evidence Gap tracking isn\'t wired into Weekly Review yet — treat current findings as provisional, not settled.',
      available: false,
    },
  ];
  if (hasStrategicSignal) {
    items.push({ key: 'personal-trajectory', label: 'Personal', detail: strategicMessage, available: true });
  }
  return items;
}

const POSTURE_LABEL: Record<StrategicPosture, string> = {
  recover: 'RECOVER', protect: 'PROTECT', stabilise: 'STABILISE',
  steady: 'STEADY', re_engage: 'RE-ENGAGE', rebuild: 'REBUILD',
  engage: 'ENGAGE', redesign: 'REDESIGN',
};

function buildNextWeek(posture: StrategicPosture, message: string, carryForward: CarryForwardItem[]): WeeklyReviewSynthesis['nextWeek'] {
  const restrictive = posture === 'recover' || posture === 'protect' || posture === 'stabilise';
  return {
    posture: POSTURE_LABEL[posture],
    message,
    priorities: carryForward.slice(0, 3).map((c) => c.detail),
    avoid: restrictive ? 'Starting additional discretionary commitments unless capacity improves.' : undefined,
  };
}

function buildTechnical(sections: WorkbenchSection[]): DomainSynthesis {
  const highConf = count(sections, 'osint', 'high-confidence');
  const escalated = count(sections, 'osint', 'escalated');
  const uncorroborated = count(sections, 'osint', 'uncorroborated');
  const noActionRequired = escalated === 0;
  const headline = escalated === null
    ? "Technical intelligence couldn't be fully checked this run."
    : noActionRequired
      ? 'No escalation required this week.'
      : `${escalated} technical signal(s) crossed an escalation threshold this week.`;
  const detail = highConf === null
    ? ''
    : `${highConf} high-confidence finding(s) emerged${uncorroborated ? `; ${uncorroborated} lower-confidence signal(s) remain under automated corroboration` : ''}.`;
  return { headline, noActionRequired, detail };
}

function buildHealth(sections: WorkbenchSection[]): DomainSynthesis {
  const published = count(sections, 'health-osint', 'published');
  const flagged = count(sections, 'health-osint', 'flagged');
  const strong = count(sections, 'health-osint', 'strong');
  const noActionRequired = flagged === 0;
  const headline = flagged === null
    ? "Health intelligence couldn't be fully checked this run."
    : noActionRequired
      ? 'No new safety escalation this week.'
      : `${flagged} FDA-flagged adverse event(s) this week — review required.`;
  const detail = published === null
    ? ''
    : `${published} new/updated evidence item(s) this week${strong ? `, ${strong} high-confidence` : ''}.`;
  return { headline, noActionRequired, detail };
}

function buildWeekInReview(
  sections: WorkbenchSection[],
  posture: StrategicPosture,
  technical: DomainSynthesis,
  health: DomainSynthesis,
  carryForwardCount: number,
): WeekInReview {
  const restrictive = posture === 'recover' || posture === 'protect' || posture === 'stabilise';
  const blocked = count(sections, 'content', 'blocked');
  const repeated = count(sections, 'agent-status', 'repeated');

  const narrativeParts: string[] = [];
  narrativeParts.push(restrictive ? 'A constrained week for personal capacity.' : 'A steady week for personal capacity.');
  narrativeParts.push(technical.noActionRequired ? 'The external technical environment remained stable.' : 'Technical signal activity required attention.');
  if (restrictive) narrativeParts.push('Recommend reducing discretionary commitments next week.');

  const lines: WeekInReview['lines'] = [
    {
      key: 'recovery', label: 'Recovery',
      glyph: restrictive ? 'down' : 'flat',
      detail: POSTURE_LABEL[posture],
    },
    {
      key: 'intelligence', label: 'Intelligence',
      glyph: technical.noActionRequired ? 'ok' : 'warn',
      detail: technical.detail || technical.headline,
    },
    {
      key: 'content', label: 'Content',
      glyph: blocked !== null && blocked > 0 ? 'warn' : 'flat',
      detail: blocked === null ? 'Not checked this run.' : blocked > 0 ? `${blocked} item(s) blocked / awaiting decision.` : 'Nothing blocked.',
    },
    {
      key: 'systems', label: 'Systems',
      glyph: repeated !== null && repeated > 0 ? 'warn' : 'ok',
      detail: repeated === null ? 'Not checked this run.' : repeated > 0 ? `${repeated} repeated failure(s).` : 'No repeated failures.',
    },
    {
      key: 'decisions', label: 'Decisions',
      glyph: carryForwardCount > 0 ? 'warn' : 'ok',
      detail: `${carryForwardCount} deserve carry-forward.`,
    },
  ];

  return { narrative: narrativeParts.join(' '), lines };
}

export function buildSynthesis(
  sections: WorkbenchSection[],
  priorSignalCounts: Record<string, number> | null,
  strategicPosture: StrategicPosture,
  strategicPostureMessage: string,
  hasStrategicSignal: boolean,
): WeeklyReviewSynthesis {
  const technical = buildTechnical(sections);
  const health = buildHealth(sections);
  const carryForward = buildCarryForward(sections, strategicPosture);
  const nextWeek = buildNextWeek(strategicPosture, strategicPostureMessage, carryForward);
  const weekInReview = buildWeekInReview(sections, strategicPosture, technical, health, carryForward.length);

  return {
    weekInReview,
    whatChanged: buildWhatChanged(sections, priorSignalCounts),
    whatMattered: buildWhatMattered(sections),
    learned: buildLearned(sections, strategicPostureMessage, hasStrategicSignal),
    carryForward,
    youCanIgnore: buildYouCanIgnore(sections),
    watchNextWeek: buildWatchNextWeek(sections, strategicPostureMessage, hasStrategicSignal),
    nextWeek,
    technical,
    health,
  };
}
