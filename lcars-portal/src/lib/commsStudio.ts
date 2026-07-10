// EOS Phase 2 Priority 5 — Executive Communications Studio: deterministic,
// evidence-cited document assembly.
//
// No LLM call anywhere in this file, deliberately. This session's Priority
// 5 audit found three separate, unreconciled LLM-writing paths already in
// the codebase (api/comms/generate/route.ts, platform-runtime/lib/comms/
// drafting.py, core/content/draft_worker.py) and no platform-wide citation
// model to check any of them against. Adding a fourth free-form generator
// would duplicate rather than compose, and risks exactly what this mission
// forbids ("never fabricate information"). This module instead reuses the
// principle core/platform/captain_brief_orchestrator.py already commits
// to - "deterministic, template-based, no LLM call: every sentence traces
// directly to a countable fact" - for every document type below. Every
// assembler here reads only real rows/fields already returned by an
// existing, canonical source; it never invents prose about what those
// fields might mean.

import { createSupabaseBrowserClient } from './supabase-browser';

export type StudioDocType = 'executive_brief' | 'decision_brief' | 'mission_report';

export interface StudioAssembly {
  title: string;
  body: string;
  evidence: string[];
}

interface CaptainBriefRecommendation {
  description: string;
  evidence: string[];
}

interface CaptainBriefItem {
  reason: string;
  recommendation: CaptainBriefRecommendation | null;
}

interface CaptainBriefDocument {
  generated_at: string;
  summary: string;
  priorities: CaptainBriefItem[];
  recommendations: CaptainBriefRecommendation[];
  warnings: CaptainBriefItem[];
  next_actions: string[];
}

/** Renders a raw Python isoformat timestamp ("2026-07-10 08:17:03.991378+00:00")
 * as a human-readable date/time. Falls back to the raw string on any parse
 * failure - a malformed value should still surface, not vanish silently. */
function formatGeneratedAt(raw: string): string {
  const d = new Date(raw.replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString('en-AU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

/** Reuses /api/captain-brief as-is (core/platform/captain_brief_orchestrator.py,
 * MSN-0313) — the most mature evidence-cited, no-fabrication document
 * assembly already in the platform. This function only reformats its
 * existing fields into a shareable document; it derives no new claims. */
async function assembleExecutiveBrief(): Promise<StudioAssembly | null> {
  try {
    const resp = await fetch('/api/captain-brief');
    if (!resp.ok) return null;
    const doc = (await resp.json()) as CaptainBriefDocument;
    if (!doc || typeof doc.summary !== 'string') return null;

    // Real bug found via a live walkthrough (2026-07-10): doc.generated_at is
    // a raw Python isoformat timestamp with microseconds
    // ("2026-07-10 08:17:03.991378+00:00") - fine as machine-readable data,
    // not fine unformatted in a document meant to read as "executive
    // quality." formatGeneratedAt() renders it the way a human reads a
    // timestamp; falls back to the raw string only if parsing fails, so a
    // malformed value still surfaces rather than silently disappearing.
    const lines: string[] = [`# Executive Brief`, `_Generated ${formatGeneratedAt(doc.generated_at)}_`, '', doc.summary];

    if (doc.priorities?.length) {
      lines.push('', '## Priorities');
      doc.priorities.forEach((p) => lines.push(`- ${p.reason}`));
    }
    if (doc.warnings?.length) {
      lines.push('', '## Warnings');
      doc.warnings.forEach((w) => lines.push(`- ${w.reason}`));
    }
    if (doc.recommendations?.length) {
      lines.push('', '## Recommendations');
      doc.recommendations.forEach((r) => lines.push(`- ${r.description}`));
    }
    if (doc.next_actions?.length) {
      lines.push('', '## Next Actions');
      doc.next_actions.forEach((a) => lines.push(`- ${a}`));
    }

    const evidence = Array.from(
      new Set([
        ...doc.priorities.flatMap((p) => p.recommendation?.evidence ?? []),
        ...doc.recommendations.flatMap((r) => r.evidence ?? []),
      ])
    );

    return { title: `Executive Brief — ${doc.generated_at.slice(0, 10)}`, body: lines.join('\n'), evidence };
  } catch {
    return null;
  }
}

/** Wraps one real decide_ledger row (STARSHIP-REDESIGN.md §5's append-only
 * decision log) - the same table Decide itself writes to on every
 * approve/hold/undo. Every field in the document is a real column value;
 * nothing here infers intent beyond what the ledger actually recorded. */
async function assembleDecisionBrief(refId: string): Promise<StudioAssembly | null> {
  if (!refId) return null;
  const supabase = createSupabaseBrowserClient();
  const { data, error } = await supabase.from('decide_ledger').select('*').eq('id', refId).maybeSingle();
  if (error || !data) return null;

  const lines = [
    `# Decision Brief`,
    `_Decided ${data.decided_at}_`,
    '',
    `**Question:** ${data.question}`,
    `**Action taken:** ${data.action}`,
    `**Source:** ${data.source} (${data.item_ref})`,
  ];
  if (data.prior_status) lines.push(`**Prior status:** ${data.prior_status}`);
  if (data.outcome) lines.push(`**Outcome:** ${data.outcome}`);
  lines.push('', `Undo available: ${data.undo_available ? 'yes' : 'no'}`);

  return {
    title: `Decision Brief — ${String(data.question)}`,
    body: lines.join('\n'),
    evidence: [`decide_ledger:${data.id}`, `${data.source}:${data.item_ref}`],
  };
}

/** Wraps one real missions row plus every decide_ledger entry recorded
 * against it (source='mission', item_ref=mission_id — the same join
 * lib/decide.ts's own fetchDecideMissionItems() convention establishes).
 * No status/outcome narrative is invented beyond what those rows say. */
async function assembleMissionReport(refId: string): Promise<StudioAssembly | null> {
  if (!refId) return null;
  const supabase = createSupabaseBrowserClient();
  const { data: mission, error } = await supabase
    .from('missions')
    .select('mission_id, title, status, priority, description')
    .eq('mission_id', refId)
    .maybeSingle();
  if (error || !mission) return null;

  const { data: decisions } = await supabase
    .from('decide_ledger')
    .select('id, question, action, decided_at, outcome')
    .eq('source', 'mission')
    .eq('item_ref', refId)
    .order('decided_at', { ascending: false });

  const lines = [
    `# Mission Report — ${mission.mission_id}`,
    '',
    `**Title:** ${mission.title}`,
    `**Status:** ${mission.status}`,
    `**Priority:** ${mission.priority ?? 'unset'}`,
  ];
  if (mission.description) lines.push('', mission.description);
  if (decisions?.length) {
    lines.push('', '## Decisions');
    decisions.forEach((d) =>
      lines.push(
        `- ${d.question} — ${d.action} (${String(d.decided_at).slice(0, 10)})${d.outcome ? `, outcome: ${d.outcome}` : ''}`
      )
    );
  }

  return {
    title: `Mission Report — ${mission.title}`,
    body: lines.join('\n'),
    evidence: [`missions:${mission.mission_id}`, ...(decisions ?? []).map((d) => `decide_ledger:${d.id}`)],
  };
}

/** Returns null on any failure to assemble - a Communications Studio caller
 * degrades to "couldn't assemble this document" rather than a fabricated
 * empty-but-successful draft, matching lib/investigate.ts's and
 * lib/recommendations.ts's own established convention. */
export async function assembleStudioDraft(type: StudioDocType, refId: string): Promise<StudioAssembly | null> {
  if (type === 'executive_brief') return assembleExecutiveBrief();
  if (type === 'decision_brief') return assembleDecisionBrief(refId);
  if (type === 'mission_report') return assembleMissionReport(refId);
  return null;
}
