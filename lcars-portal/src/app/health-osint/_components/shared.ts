// Shared types/helpers for the Health OSINT Today/My Evidence/Library
// views (Phase 2 Three-Workbench Simplification mission).

import type { StateTone } from '@/lib/types';

// Terminology mapping, mission spec §16 — internal vocabulary stays in the
// API payloads (disposition/evidence_contribution enums), this is purely a
// display-layer translation so the UI never shows a raw enum to the user.
export const EVIDENCE_CONTRIBUTION_LABEL: Record<string, string> = {
  CONFIRMS: 'Supports current view',
  CHALLENGES: 'Challenges current view',
  EXTENDS: 'Adds new evidence',
  REPLICATION: 'Replicated',
  SAFETY: 'Safety',
  BACKGROUND: 'Background/Reference',
  UNRESOLVED: 'Unresolved',
};

export const CONFIDENCE_LABEL: Record<string, string> = {
  high: 'Strong evidence',
  medium: 'Moderate evidence',
  low: 'Limited evidence',
  unknown: 'Evidence unclear',
};

export const STRENGTH_LABEL: Record<string, string> = {
  STRONG: 'Strong',
  MODERATE: 'Moderate',
  LIMITED: 'Limited',
};

export const TREND_LABEL: Record<string, string> = {
  up: '↑ Strengthening',
  down: '↓ Weakening',
  stable: '→ Stable',
  mixed: '↕ Mixed',
  unknown: 'Not enough data yet',
};

export function strengthTone(strength: string): StateTone {
  if (strength === 'STRONG') return 'ok';
  if (strength === 'MODERATE') return 'warn';
  return 'unknown';
}

export function trendTone(trend: string): StateTone {
  if (trend === 'up') return 'ok';
  if (trend === 'down') return 'crit';
  if (trend === 'stable') return 'unknown';
  return 'unknown';
}

export interface EvidenceItem {
  signal_id: string;
  title: string;
  summary: string | null;
  source_url: string | null;
  source_name: string;
  topic_key?: string;
  topic_label?: string;
  confidence_level: string;
  study_design?: string | null;
  sample_size?: number | null;
  published_at?: string | null;
  collected_at: string;
  evidence_contribution: string | null;
  disposition?: string | null;
  safety_relevance: boolean;
  actionable_recommendation?: string | null;
}

export interface TopicSummary {
  topic_key: string;
  topic_label: string;
  strength: 'STRONG' | 'MODERATE' | 'LIMITED';
  trend: 'up' | 'down' | 'stable' | 'mixed' | 'unknown';
  last_changed: string | null;
  safety_relevant: boolean;
  composition: { high: number; medium: number; low: number; unknown: number };
}

// Shared human-feedback reason vocabulary — mirrors
// api/health-osint-curation/[id]/reject/route.ts's VALID_FEEDBACK_REASONS
// (migration 0186 CHECK constraint), just presented as the friendlier
// prompt-list the mission spec calls for on the folded-in review card.
export const IGNORE_REASONS: { value: string; label: string }[] = [
  { value: 'IRRELEVANT_TOPIC', label: 'Irrelevant' },
  { value: 'WRONG_POPULATION', label: 'Wrong population' },
  { value: 'WEAK_EVIDENCE', label: 'Weak evidence' },
  { value: 'ALREADY_KNOWN', label: 'Already known' },
  { value: 'DUPLICATE', label: 'Duplicate' },
  { value: 'LOW_INFORMATION_VALUE', label: 'Low information value' },
  { value: 'OTHER', label: 'Other' },
];
