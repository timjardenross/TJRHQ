// computeInterventionEffectiveness() — extracted out of route.ts (rather
// than exported from it) because Next.js App Router route files only
// permit HTTP-method exports (GET/POST/etc.) plus a small allow-list of
// route config — any other named export fails `next build`'s generated
// route-type check (`tsc --noEmit` surfaces it as a TS2344 on
// .next/types/app/api/human-systems/route.ts). Living here lets the unit
// test import this function directly with a stubbed `sb`, without mocking
// the whole GET handler's auth/session plumbing.

import type { InterventionEffectiveness } from '@/app/human-systems-workbench/_components/types';

const MIN_SAMPLE_FOR_EFFECTIVENESS = 3; // mirrors the bot's intervention_engine.py MIN_SAMPLE_FOR_WEIGHTING

/** What Helps Me (spec §18) — TypeScript mirror of the Capacity Bot's
 *  personal_effectiveness_summary() (intervention_engine.py). All-time,
 *  same as the bot (no window filter) — counts accumulate meaning over
 *  time, and this is exactly the same query the bot's /actions and this
 *  workbench should never disagree on. */
export async function computeInterventionEffectiveness(sb: any): Promise<InterventionEffectiveness[]> {
  const [{ data: events }, { data: catalogueRows }] = await Promise.all([
    sb.from('capacity_intervention_events').select('intervention_id,outcome,help_state'),
    // evidence_strength/evidence_basis: V3 doc §16 "Evidence Metadata"
    // (migration 0157) — general evidence metadata, kept separate from
    // the personal better/same/worse counts computed below. evidence_
    // strength defaults to 'unknown' at the DB layer so every one of the
    // 30 originally-seeded rows resolves it explicitly rather than null.
    sb.from('capacity_interventions').select('intervention_id,title,evidence_strength,evidence_basis'),
  ]);
  const catalogue = new Map<string, { title: string; evidence_strength: InterventionEffectiveness['evidence_strength']; evidence_basis: string | null }>(
    (catalogueRows ?? []).map((r: any) => [
      r.intervention_id,
      { title: r.title, evidence_strength: r.evidence_strength ?? 'unknown', evidence_basis: r.evidence_basis ?? null },
    ]),
  );
  const byId = new Map<string, { outcome: string | null; help_state: string | null }[]>();
  for (const e of (events ?? []) as any[]) {
    const arr = byId.get(e.intervention_id) ?? [];
    arr.push({ outcome: e.outcome, help_state: e.help_state });
    byId.set(e.intervention_id, arr);
  }
  const out: InterventionEffectiveness[] = [];
  for (const [intervention_id, rows] of byId) {
    const attempts = rows.length;
    const better = rows.filter((r) => r.outcome === 'better').length;
    const same = rows.filter((r) => r.outcome === 'same').length;
    const worse = rows.filter((r) => r.outcome === 'worse').length;
    const not_completed = rows.filter((r) => !r.outcome || r.outcome === 'not_completed').length;
    const stateCounts = new Map<string, number>();
    for (const r of rows) if (r.help_state) stateCounts.set(r.help_state, (stateCounts.get(r.help_state) ?? 0) + 1);
    const common_context = stateCounts.size
      ? Array.from(stateCounts.entries()).sort((a, b) => b[1] - a[1])[0][0].replace(/_/g, ' ')
      : null;
    const cat = catalogue.get(intervention_id);
    out.push({
      intervention_id, title: cat?.title ?? intervention_id, attempts, better, same, worse, not_completed,
      meets_sample_threshold: attempts >= MIN_SAMPLE_FOR_EFFECTIVENESS, common_context,
      evidence_strength: cat?.evidence_strength ?? 'unknown', evidence_basis: cat?.evidence_basis ?? null,
    });
  }
  return out.sort((a, b) => b.attempts - a.attempts);
}
