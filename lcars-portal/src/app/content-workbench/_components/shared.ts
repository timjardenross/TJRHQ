// Shared constants for the Content Workbench (COMMS-002).
// Same TJR Design System conventions as comms-workbench/_components/shared.ts
// (wb-* tokens, @/components/ui) — this workbench is additive, not a fork of
// that one; PILLAR_LABEL is intentionally duplicated rather than imported so
// this workbench has zero import dependency on comms-workbench/_components/
// (per the design-system barrel rule: never reach into a sibling workbench's
// _components/).

import type { BadgeStatus } from '@/components/ui';

export type Stage = 'capture' | 'research' | 'content_prep' | 'proofing';

export const STAGE_LABEL: Record<Stage, string> = {
  capture: 'Capture',
  research: 'Research',
  content_prep: 'Content Prep',
  proofing: 'Proofing',
};

export const STAGE_HINT: Record<Stage, string> = {
  capture: 'Needs a research brief before a draft can be generated.',
  research: 'Briefed — ready to generate a draft.',
  content_prep: 'Drafting and editing. Submit for review when ready.',
  proofing: 'QA checklist + sign-off. Advancing past Approved happens in the Communications Workbench.',
};

export const PILLAR_LABEL: Record<string, string> = {
  operational_resilience: 'Operational Resilience',
  business_continuity: 'Business Continuity',
  human_performance: 'Human Performance',
  wellness_sustainable_performance: 'Wellness',
  ai_augmented_leadership: 'AI-Augmented Leadership',
  personal_operating_systems: 'Personal OS',
  future_of_work: 'Future of Work',
  decision_quality_governance: 'Decision Quality',
};

export interface ContentItem {
  id: string;
  title: string;
  pillar: string | null;
  status: 'opportunity' | 'draft' | 'review' | 'approved';
  stage: Stage;
  source_kind: string | null;
  source_ref: string | null;
  signal_source_id: string | null;
  notes: string | null;
  body: string | null;
  draft_generated_at: string | null;
  sensitive: boolean;
  research_notes: string | null;
  research_sources: Array<{ label?: string; url?: string }> | null;
  research_angle: string | null;
  research_completed_at: string | null;
  qa_checklist: Record<string, unknown> | null;
  qa_status: 'pending' | 'qa_passed' | 'qa_failed' | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rank_score: number | null;
  capture_scored: boolean;
  captain_focus: boolean;
  created_at: string;
  updated_at: string;
}

/** rank_score is 0-100 (same scale as content_signals.rank_score). */
export function rankBadgeStatus(score: number | null): BadgeStatus {
  if (score === null) return 'neutral';
  if (score >= 70) return 'success';
  if (score >= 45) return 'warning';
  return 'neutral';
}

export const QA_CHECKLIST_ITEMS: Array<{ key: 'accuracy' | 'brand_voice' | 'compliance' | 'links_checked'; label: string }> = [
  { key: 'accuracy', label: 'Facts and figures verified against the source' },
  { key: 'brand_voice', label: 'Tone matches — reputation over reach, no hype' },
  { key: 'compliance', label: 'No sensitive workplace, client, or health detail exposed' },
  { key: 'links_checked', label: 'Links (if any) resolve and match the claim' },
];
