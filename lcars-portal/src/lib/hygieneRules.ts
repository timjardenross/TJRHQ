import { TERMINAL_STATUSES } from '@/lib/missionStatus';

/**
 * Mission IDs minted by the retired Slack/force-triage pipeline
 * (e.g. "force-20260610225359", "slack-20260611175431") — synthetic stub
 * missions, not real work. All of them happen to already be Archived, but
 * this checks the ID directly rather than depending on that staying true.
 */
export function isGeneratedJunkMissionId(missionId: string): boolean {
  return /^(force|slack)-\d+$/.test(missionId);
}

/**
 * Single gate every mission-scoped hygiene signal must pass before it's
 * pushed. Centralising this (rather than re-deriving a status filter per
 * rule) is what makes "no closed mission can ever reappear" a property of
 * the code, not of each rule author remembering to write the filter — and
 * the original bug was exactly a rule author getting the filter wrong
 * (case-mismatched 'CLOSED' instead of 'Closed', missing 'Archived'
 * entirely).
 */
export function isHygieneEligible(status: string, missionId: string): boolean {
  return !TERMINAL_STATUSES.includes(status) && !isGeneratedJunkMissionId(missionId);
}

interface MissionScopedSignal {
  mission_id?: string;
  severity: 'critical' | 'high' | 'medium';
}

const SEVERITY_RANK: Record<MissionScopedSignal['severity'], number> = {
  critical: 0,
  high: 1,
  medium: 2,
};

/**
 * Collapses multiple signals about the same mission_id down to one (the
 * most severe). Signals with no mission_id (log-gap, recovery-gap) pass
 * through untouched — they're not about a specific mission so there's
 * nothing to dedupe.
 */
export function dedupeMissionSignals<T extends MissionScopedSignal>(signals: T[]): T[] {
  const bestByMission = new Map<string, T>();
  const unscoped: T[] = [];

  for (const signal of signals) {
    if (!signal.mission_id) {
      unscoped.push(signal);
      continue;
    }
    const existing = bestByMission.get(signal.mission_id);
    if (!existing || SEVERITY_RANK[signal.severity] < SEVERITY_RANK[existing.severity]) {
      bestByMission.set(signal.mission_id, signal);
    }
  }

  return [...unscoped, ...bestByMission.values()];
}
