import type { BadgeStatus } from '@/components/ui/Badge';
import type { StateTone } from '@/lib/types';

/** Governance registry: new UI copy and tokens must use these canonical terms. */
export const CANONICAL_TERMS = {
  hub: 'LifeOS Hub',
  briefs: 'Briefs',
  emergencyAlerts: 'Emergency Alerts',
  humanSystems: 'Human Systems',
  needsAction: 'Needs action',
  awaitingOwner: 'Awaiting owner',
  noAction: 'No action needed',
  unavailable: 'Unavailable',
  stale: 'Stale',
} as const;

export const LEGACY_TERM_REPLACEMENTS: Record<string, string> = {
  Home: CANONICAL_TERMS.hub,
  "Captain's Brief": CANONICAL_TERMS.briefs,
  Medical: CANONICAL_TERMS.humanSystems,
  Alerts: CANONICAL_TERMS.emergencyAlerts,
};

export type Density = 'comfortable' | 'compact' | 'data-dense';

export const DENSITY_CLASSES: Record<Density, string> = {
  comfortable: 'gap-4 p-4 text-sm',
  compact: 'gap-2 p-3 text-xs',
  'data-dense': 'gap-1.5 p-2 text-xs leading-tight',
};

export const STATUS_TONE_TO_BADGE: Record<StateTone, BadgeStatus> = {
  ok: 'success', warn: 'warning', crit: 'error', info: 'info', unknown: 'neutral',
};

export interface PrimaryActionContract {
  label: string;
  href: string;
}

export function validatePrimaryAction(action: PrimaryActionContract | null | undefined): string[] {
  if (!action) return ['missing primary action'];
  const errors: string[] = [];
  if (!action.label.trim()) errors.push('primary action label is empty');
  if (!action.href.startsWith('/')) errors.push('primary action must use an internal route');
  if (/^(open|click|submit|go)$/i.test(action.label.trim())) errors.push('primary action needs a specific verb');
  return errors;
}
