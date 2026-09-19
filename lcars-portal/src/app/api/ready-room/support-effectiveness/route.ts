/**
 * Ready Room personal-effectiveness read path — GET /api/ready-room/support-effectiveness
 *
 * Mission 5 (Evidence & Adaptive Support). Two callers need this:
 *   (a) explainability — "why are you suggesting this" (spec §30): the
 *       per-intervention attempts/better/worse counts and whether they
 *       clear the sample floor.
 *   (b) ordering — which support Ready Room offers first in a given
 *       context (spec §17/§20/§29): a Captain-stated preference
 *       (capacity_preferences, domain='ready_room') always outranks
 *       historical evidence, and 'do_not_suggest' removes an intervention
 *       from the list entirely regardless of positive history.
 *
 * Same MIN_SAMPLE=3 floor and "personal vs general evidence never
 * blended" discipline as computeInterventionEffectiveness() (see that
 * file's header comment) — this route is a domain='ready_room' read
 * through the exact same function, not a second evidence engine.
 */

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { computeInterventionEffectiveness } from '../../human-systems/intervention-effectiveness';

interface PreferenceRow {
  item_code: string | null;
  preference_state: 'preferred' | 'do_not_suggest' | null;
  note: string | null;
}

export interface ReadyRoomSupportRanking {
  intervention_id: string;
  title: string;
  attempts: number;
  better: number;
  same: number;
  worse: number;
  not_completed: number;
  meets_sample_threshold: boolean;
  preference_state: 'preferred' | 'do_not_suggest' | null;
  preference_note: string | null;
  /** One-line, Captain-facing "why this" answer (spec §30) — built from
   *  whichever evidence actually exists; never fabricates confidence
   *  below the sample floor. */
  reason: string;
}

function buildReason(row: {
  attempts: number; better: number; worse: number; meets_sample_threshold: boolean;
}, preference: PreferenceRow | undefined): string {
  if (preference?.preference_state === 'preferred') {
    return preference.note ? `You've asked to be offered this: ${preference.note}` : "You've asked to be offered this.";
  }
  if (!row.meets_sample_threshold) {
    return row.attempts === 0
      ? 'Not tried yet — no personal evidence either way.'
      : `Only ${row.attempts} time${row.attempts === 1 ? '' : 's'} so far — not enough to say if it usually helps.`;
  }
  if (row.better > row.worse) return `Helped ${row.better} of ${row.attempts} times you've used it.`;
  if (row.worse > row.better) return `Hasn't helped ${row.worse} of ${row.attempts} times you've used it.`;
  return `Mixed results over ${row.attempts} tries.`;
}

export async function GET(_req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const sb = await createSupabaseServerClient();
    const [effectiveness, { data: preferenceRows }] = await Promise.all([
      computeInterventionEffectiveness(sb, 'ready_room'),
      sb.from('capacity_preferences').select('item_code,preference_state,note').eq('domain', 'ready_room'),
    ]);
    const preferenceByCode = new Map<string, PreferenceRow>(
      ((preferenceRows ?? []) as PreferenceRow[])
        .filter((p) => p.item_code)
        .map((p) => [p.item_code as string, p]),
    );

    // computeInterventionEffectiveness only returns rows with at least one
    // event — a catalogue entry nobody has used yet still needs to appear
    // (attempts: 0, "not tried yet") so ordering/explainability cover all
    // four seeded ready_room interventions from day one, not just ones
    // with history.
    const { data: catalogueRows } = await sb
      .from('capacity_interventions')
      .select('intervention_id,title')
      .eq('domain', 'ready_room');
    const seen = new Set(effectiveness.map((e) => e.intervention_id));
    const zeroAttempt = ((catalogueRows ?? []) as { intervention_id: string; title: string }[])
      .filter((c) => !seen.has(c.intervention_id))
      .map((c) => ({
        intervention_id: c.intervention_id, title: c.title, attempts: 0, better: 0, same: 0, worse: 0,
        not_completed: 0, meets_sample_threshold: false, common_context: null,
        evidence_strength: 'unknown' as const, evidence_basis: null,
      }));

    const all = [...effectiveness, ...zeroAttempt].filter(
      (row) => preferenceByCode.get(row.intervention_id)?.preference_state !== 'do_not_suggest',
    );

    const ranked: ReadyRoomSupportRanking[] = all
      .map((row) => {
        const preference = preferenceByCode.get(row.intervention_id);
        return {
          intervention_id: row.intervention_id,
          title: row.title,
          attempts: row.attempts,
          better: row.better,
          same: row.same,
          worse: row.worse,
          not_completed: row.not_completed,
          meets_sample_threshold: row.meets_sample_threshold,
          preference_state: preference?.preference_state ?? null,
          preference_note: preference?.note ?? null,
          reason: buildReason(row, preference),
        };
      })
      .sort((a, b) => {
        // Captain-stated preference outranks historical inference (spec
        // §17/§29) — 'preferred' always sorts first.
        const aPreferred = a.preference_state === 'preferred' ? 1 : 0;
        const bPreferred = b.preference_state === 'preferred' ? 1 : 0;
        if (aPreferred !== bPreferred) return bPreferred - aPreferred;
        // Below the sample floor, evidence isn't strong enough to reorder
        // on — keep catalogue order (stable sort) rather than let a
        // single lucky/unlucky attempt jump an intervention around.
        if (a.meets_sample_threshold !== b.meets_sample_threshold) {
          return (b.meets_sample_threshold ? 1 : 0) - (a.meets_sample_threshold ? 1 : 0);
        }
        if (!a.meets_sample_threshold) return 0;
        const aRatio = a.attempts ? (a.better - a.worse) / a.attempts : 0;
        const bRatio = b.attempts ? (b.better - b.worse) / b.attempts : 0;
        return bRatio - aRatio;
      });

    return NextResponse.json({ items: ranked });
  } catch (err) {
    console.error('[ready-room/support-effectiveness] read failed:', err);
    return NextResponse.json({ error: 'support_effectiveness_read_failed' }, { status: 500 });
  }
}
