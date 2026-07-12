// Shared constants for the Communications Workbench (Phase 1C).
// Mirrors intelligence-workbench: standalone Shell (no LCARS app chrome),
// TJR Design System components (@/components/ui), wb-* tokens.

import type { BadgeStatus } from '@/components/ui';

export type Domain = 'health' | 'operational' | 'both';
export type Status = 'opportunity' | 'draft' | 'review' | 'approved' | 'ready_to_publish' | 'published';

export const STATUS_LABEL: Record<string, string> = {
  opportunity: 'Opportunity',
  draft: 'Draft',
  review: 'Review',
  approved: 'Approved',
  ready_to_publish: 'Ready to Publish',
  published: 'Published',
};

export const STATUS_BADGE: Record<string, BadgeStatus> = {
  opportunity: 'neutral',
  draft: 'info',
  review: 'warning',
  approved: 'success',
  ready_to_publish: 'info',
  published: 'neutral',
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

export const DOMAIN_BADGE: Record<string, BadgeStatus> = {
  health: 'info',
  operational: 'neutral',
};

export const FORMATS = [
  { key: 'linkedin_post', label: 'LinkedIn Post' },
  { key: 'executive_insight', label: 'Executive Insight' },
  { key: 'lessons_learned', label: 'Lessons Learned' },
  { key: 'case_study', label: 'Case Study' },
  { key: 'industry_commentary', label: 'Industry Commentary' },
  { key: 'article_draft', label: 'Article Draft' },
];

// Pipeline stages a card can advance through, in order, and the trigger
// each transition needs. Mirrors TRANSITIONS in
// api/comms/[id]/advance/route.ts — do not fork this list, that route is
// the single canonical place status transitions are enforced.
export const NEXT_TRIGGER: Record<string, { trigger: string; label: string }> = {
  draft: { trigger: 'officer_submitted', label: 'Submit for Review' },
  review: { trigger: 'captain_approved', label: 'Approve' },
  approved: { trigger: 'captain_confirmed', label: 'Confirm Ready to Publish' },
  ready_to_publish: { trigger: 'mark_published', label: 'Submit for Publish Approval' },
};

export function toMarkdown(item: { title: string; pillar: string | null; body: string | null; updated_at: string }) {
  const lines = [`# ${item.title}`, ''];
  if (item.body) lines.push(item.body, '');
  lines.push('---', `**Pillar:** ${PILLAR_LABEL[item.pillar ?? ''] ?? item.pillar ?? '—'}`);
  lines.push(`**Published:** ${item.updated_at.slice(0, 10)}`);
  return lines.join('\n');
}

export function toPlainText(item: { title: string; pillar: string | null; body: string | null; updated_at: string }) {
  const lines = [item.title, ''];
  if (item.body) lines.push(item.body, '');
  lines.push(`Pillar: ${PILLAR_LABEL[item.pillar ?? ''] ?? item.pillar ?? '—'}`);
  lines.push(`Published: ${item.updated_at.slice(0, 10)}`);
  return lines.join('\n');
}

export function download(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
