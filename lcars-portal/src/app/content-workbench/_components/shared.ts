// Shared constants for the Content Workbench (COMMS-002).
// Same TJR Design System conventions as comms-workbench/_components/shared.ts
// (wb-* tokens, @/components/ui) — this workbench is additive, not a fork of
// that one; PILLAR_LABEL is intentionally duplicated rather than imported so
// this workbench has zero import dependency on comms-workbench/_components/
// (per the design-system barrel rule: never reach into a sibling workbench's
// _components/).
//
// 2026-08 visual redesign (agency-tool pass, Content Workbench only — see
// ContentBoard.tsx/CaptureBox.tsx): STAGE_ACCENT below is the one new piece
// of shared state it needed — a maturity-gradient palette (neutral -> sage
// -> amber -> green) reusing only existing wb-* tokens, no new Tailwind
// config. No other workbench reads this file, so this stays scoped.

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
  proofing: 'QA checklist, sign-off, and publish submission — the Captain still approves the final publish in Decide.',
};

/**
 * Maturity-gradient accent per stage — neutral (just captured) through sage
 * (briefed) and amber (in progress) to green (proofed/ready). Used for the
 * column top-bar, the card's left rail, and the pipeline overview strip.
 * Deliberately reuses only existing wb-* tokens (ok/warn/sage/line) — the
 * same hues STATUS_BADGE already uses over in comms-workbench/shared.ts —
 * so this reads as "the same app," not a new brand.
 */
export const STAGE_ACCENT: Record<Stage, { icon: string; bar: string; chip: string; header: string; ring: string }> = {
  capture: { icon: '✉', bar: 'bg-wb-ink2/50', chip: 'bg-wb-line text-wb-ink2', header: 'bg-wb-ink2/5', ring: 'border-wb-ink2/30' },
  research: { icon: '◎', bar: 'bg-wb-sage', chip: 'bg-wb-sage/15 text-wb-sage-deep', header: 'bg-wb-sage/8', ring: 'border-wb-sage/40' },
  content_prep: { icon: '✎', bar: 'bg-wb-warn', chip: 'bg-wb-warn/15 text-wb-warn-on', header: 'bg-wb-warn/8', ring: 'border-wb-warn/40' },
  proofing: { icon: '✓', bar: 'bg-wb-ok', chip: 'bg-wb-ok/15 text-wb-ok-on', header: 'bg-wb-ok/8', ring: 'border-wb-ok/40' },
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
  status: 'opportunity' | 'draft' | 'review' | 'approved' | 'ready_to_publish';
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
