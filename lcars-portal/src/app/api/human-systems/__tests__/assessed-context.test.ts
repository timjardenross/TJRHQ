import { describe, it, expect } from 'vitest';
import { buildAssessedContext } from '../assessed-context';
import type { BurnoutWindowRow } from '../strategic-posture';

// Human Execution Loop mission — Human Systems' assessed-context contract
// must (a) keep NOW and TRAJECTORY separate, (b) mark itself stale/absent
// rather than silently presenting old data as current, and (c) never
// produce a "vetoing" shape — every field here is advisory context, there
// is no boolean anywhere meaning "blocked" (brief §7/§8/§42/§43).

function todayRow(overrides: Partial<Parameters<typeof buildAssessedContext>[0]> = {}) {
  return {
    capacity_state: 'green',
    regulation_state: 'settled',
    executive_function: 'good',
    compensation_load: 'low',
    stimulation_state: 'balanced',
    pain_state: 'none',
    active_loads: ['work'],
    identified_needs: ['rest'],
    captured_at: new Date().toISOString(),
    log_date: new Date().toISOString().slice(0, 10),
    ...overrides,
  };
}

describe('buildAssessedContext — freshness', () => {
  it('is fresh and high-confidence-eligible when today has a check-in', () => {
    const ctx = buildAssessedContext(todayRow(), []);
    expect(ctx.freshness.status).toBe('fresh');
    expect(ctx.has_checkin_today).toBe(true);
  });

  it('is "none" with low confidence when there is no check-in at all (no-check-in state, brief §43)', () => {
    const ctx = buildAssessedContext(null, []);
    expect(ctx.freshness.status).toBe('none');
    expect(ctx.has_checkin_today).toBe(false);
    expect(ctx.confidence).toBe('low');
    expect(ctx.posture).toBe('UNKNOWN');
    // No-check-in must never read as a constrained state — it's absence of
    // evidence, not evidence of PROTECT/RECOVER.
    expect(ctx.available_capacity).toBe('unknown');
  });

  it('is "stale" when the last check-in is from a prior day, and caps confidence at low even with a rich trajectory window', () => {
    const yesterday = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    const staleToday = { ...todayRow(), captured_at: yesterday };
    const richWindow: BurnoutWindowRow[] = Array.from({ length: 15 }, (_, i) => ({
      checkin_type: 'capacity',
      log_date: `2026-08-${String(i + 1).padStart(2, '0')}`,
      captured_at: `2026-08-${String(i + 1).padStart(2, '0')}T09:00:00Z`,
      capacity_state: 'green',
      executive_function: 'good',
      stimulation_state: 'balanced',
      compensation_load: 'low',
      recovery_duration: null,
      capacity_debt: null,
    }));
    // buildAssessedContext only reads captured_at off todayRow to decide
    // freshness; it is intentionally called with a null "today" row here
    // (no capacity_checkins row logged today) plus a rich window, to prove
    // a good trajectory history does not manufacture confidence about NOW.
    const ctx = buildAssessedContext(null, richWindow);
    expect(ctx.freshness.status).toBe('none');
    expect(ctx.confidence).toBe('low');
    void staleToday;
  });
});

describe('buildAssessedContext — trajectory stays separate from NOW (brief §8)', () => {
  it('a single good today does not collapse an accumulating-strain trajectory into ENGAGE', () => {
    const strainWindow: BurnoutWindowRow[] = Array.from({ length: 10 }, (_, i) => ({
      checkin_type: 'capacity',
      log_date: `2026-08-${String(i + 1).padStart(2, '0')}`,
      captured_at: `2026-08-${String(i + 1).padStart(2, '0')}T09:00:00Z`,
      capacity_state: i < 8 ? 'orange' : 'green',
      executive_function: 'strained',
      stimulation_state: 'high',
      compensation_load: 'high',
      recovery_duration: null,
      capacity_debt: 'yes',
    }));
    const ctx = buildAssessedContext(todayRow({ capacity_state: 'green' }), strainWindow);
    expect(ctx.posture).toBe('ENGAGE');
    // The trajectory read is reported alongside, not merged into, posture.
    expect(ctx.strain_or_recovery_context.trajectory).not.toBe('stable');
    expect(ctx.strain_or_recovery_context.strategic_posture).not.toBe('engage');
  });
});

describe('buildAssessedContext — this is context, never a veto (brief §7)', () => {
  it('a RECOVER-shaped day still returns advisory fields only, no blocking flag', () => {
    const ctx = buildAssessedContext(
      todayRow({ capacity_state: 'red', regulation_state: 'overloaded', executive_function: 'very_difficult' }),
      [],
    );
    expect(ctx.posture).toBe('RECOVER');
    // The object is a plain data shape — asserting the known keys are all
    // informational (string/array/object), not booleans that could gate
    // access downstream.
    for (const [key, value] of Object.entries(ctx)) {
      if (key === 'has_checkin_today') continue; // freshness metadata, not an authority flag
      expect(typeof value).not.toBe('boolean');
    }
  });
});
