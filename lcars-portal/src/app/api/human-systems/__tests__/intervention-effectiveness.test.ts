import { describe, it, expect } from 'vitest';
import { computeInterventionEffectiveness } from '../intervention-effectiveness';

// V3 doc §16 "Evidence Metadata" — computeInterventionEffectiveness now
// also passes through capacity_interventions.evidence_strength /
// evidence_basis (migration 0157) alongside the existing personal
// better/same/worse counts. These tests lock in:
//   - the DB default ('unknown') survives even if a row somehow comes
//     back null (defence in depth — the column itself defaults too);
//   - null-safety for the 30 pre-existing seeded rows, which have no
//     evidence_basis and no catalogue match cases;
//   - evidence fields never influence attempts/better/same/worse — the
//     two are computed independently, never blended (spec §16).

function makeSb(opts: {
  events?: { intervention_id: string; outcome: string | null; help_state: string | null }[];
  catalogue?: { intervention_id: string; title: string; evidence_strength: string | null; evidence_basis: string | null }[];
}) {
  const { events = [], catalogue = [] } = opts;
  return {
    from(table: string) {
      return {
        select(_cols: string) {
          if (table === 'capacity_intervention_events') return Promise.resolve({ data: events });
          if (table === 'capacity_interventions') return Promise.resolve({ data: catalogue });
          throw new Error(`unexpected table ${table}`);
        },
      };
    },
  };
}

describe('computeInterventionEffectiveness — evidence metadata pass-through (V3 §16)', () => {
  it('passes through a real evidence_strength/evidence_basis unchanged', async () => {
    const sb = makeSb({
      events: [
        { intervention_id: 'move_5', outcome: 'better', help_state: 'flat' },
        { intervention_id: 'move_5', outcome: 'better', help_state: 'flat' },
        { intervention_id: 'move_5', outcome: 'same', help_state: null },
      ],
      catalogue: [
        {
          intervention_id: 'move_5',
          title: 'Move for 5-10 minutes',
          evidence_strength: 'moderate',
          evidence_basis: 'Some general summary',
        },
      ],
    });
    const out = await computeInterventionEffectiveness(sb);
    expect(out).toHaveLength(1);
    expect(out[0].evidence_strength).toBe('moderate');
    expect(out[0].evidence_basis).toBe('Some general summary');
    // Personal counts computed independently of the evidence fields.
    expect(out[0].attempts).toBe(3);
    expect(out[0].better).toBe(2);
    expect(out[0].same).toBe(1);
  });

  it('defaults evidence_strength to unknown and evidence_basis to null when the catalogue row has nulls (the 30 pre-existing seeded rows)', async () => {
    const sb = makeSb({
      events: [
        { intervention_id: 'rest_20', outcome: 'better', help_state: null },
        { intervention_id: 'rest_20', outcome: 'better', help_state: null },
        { intervention_id: 'rest_20', outcome: 'worse', help_state: null },
      ],
      catalogue: [
        { intervention_id: 'rest_20', title: 'Rest for 20-30 minutes', evidence_strength: null, evidence_basis: null },
      ],
    });
    const out = await computeInterventionEffectiveness(sb);
    expect(out[0].evidence_strength).toBe('unknown');
    expect(out[0].evidence_basis).toBeNull();
    expect(out[0].meets_sample_threshold).toBe(true);
  });

  it('defaults evidence_strength to unknown when there is no catalogue match at all', async () => {
    const sb = makeSb({
      events: [{ intervention_id: 'orphaned_id', outcome: 'better', help_state: null }],
      catalogue: [],
    });
    const out = await computeInterventionEffectiveness(sb);
    expect(out[0].title).toBe('orphaned_id');
    expect(out[0].evidence_strength).toBe('unknown');
    expect(out[0].evidence_basis).toBeNull();
  });

  it('returns an empty array with no events, without throwing on an empty catalogue', async () => {
    const sb = makeSb({ events: [], catalogue: [] });
    const out = await computeInterventionEffectiveness(sb);
    expect(out).toEqual([]);
  });
});
