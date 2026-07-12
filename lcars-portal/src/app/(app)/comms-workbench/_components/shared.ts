// Shared constants for the Communications Workbench (Phase 1C).
// Mirrors the palette already established by comms/page.tsx and
// intelligence/page.tsx — the dark cyan/gold mockup in
// COMMS-UI-REDESIGN-SPEC.md was a design exploration, not what the rest of
// the live app looks like, so this follows the shipped light LCARS theme.

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

export const STATUS_COLOUR: Record<string, string> = {
  opportunity: 'text-[#61718c] border-[#d9e1f0] bg-[#eef1f8]',
  draft: 'text-blue-400 border-blue-400/30 bg-blue-400/5',
  review: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/5',
  approved: 'text-green-400 border-green-400/30 bg-green-400/5',
  ready_to_publish: 'text-purple-400 border-purple-400/30 bg-purple-400/5',
  published: 'text-[#243b7a] border-[#243b7a]/30 bg-[#243b7a]/5',
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

export const DOMAIN_BADGE: Record<string, string> = {
  health: 'text-cyan-500 border-cyan-500/30 bg-cyan-500/5',
  operational: 'text-blue-500 border-blue-500/30 bg-blue-500/5',
};

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
