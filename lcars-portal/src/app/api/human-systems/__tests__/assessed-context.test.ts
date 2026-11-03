import { describe, it, expect } from 'vitest';
import { buildAssessedContext } from '../assessed-context';

// Human Execution Loop mission — Human Systems' assessed-context contract
// must (a) describe only today's reading (no multi-day trend), (b) mark itself stale/absent
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
  it('is fresh when today has a check-in', () => {
    const ctx = buildAssessedContext(todayRow());
    expect(ctx.freshness.status).toBe('fresh');
    expect(ctx.has_checkin_today).toBe(true);
  });

  it('is "none" when there is no check-in at all (no-check-in state, brief §43)', () => {
    const ctx = buildAssessedContext(null);
    expect(ctx.freshness.status).toBe('none');
    expect(ctx.has_checkin_today).toBe(false);
    expect(ctx.posture).toBe('UNKNOWN');
    // No-check-in must never read as a constrained state — it's absence of
    // evidence, not evidence of PROTECT/RECOVER.
    expect(ctx.available_capacity).toBe('unknown');
  });

  it('reports "stale" with an honest last_checkin_at when a prior check-in exists but not today (brief §42 — Monday should not silently represent Thursday)', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    // No row for today (null) — a stale prior check-in is supplied
    // separately, the way getAssessedContext() derives it from the window
    // query rather than a fabricated "today" row.
    const ctx = buildAssessedContext(null, twoDaysAgo);
    expect(ctx.freshness.status).toBe('stale');
    expect(ctx.freshness.last_checkin_at).toBe(twoDaysAgo);
    expect(ctx.has_checkin_today).toBe(false);
    // Still no posture fabricated from the stale row — NOW stays UNKNOWN.
    expect(ctx.posture).toBe('UNKNOWN');
  });

  it('has_checkin_today tracks whether a row exists for today specifically, not just recency-by-clock', () => {
    // A check-in from 2 hours ago that is nonetheless not "today's row" —
    // e.g. it's just after midnight and the last check-in was late last
    // night. freshness.status can still read 'fresh' (the evidence is
    // recent), but has_checkin_today must not claim a check-in was logged
    // for today's date, since NOW posture derivation is calendar-day scoped.
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    const ctx = buildAssessedContext(null, twoHoursAgo);
    expect(ctx.has_checkin_today).toBe(false);
    expect(ctx.posture).toBe('UNKNOWN');
  });
});

describe('buildAssessedContext — no multi-day trend', () => {
  it('describes today only: no trajectory or confidence fields', () => {
    const ctx = buildAssessedContext(todayRow({ capacity_state: 'green' }));
    expect(ctx.posture).toBe('ENGAGE');
    expect(ctx).not.toHaveProperty('strain_or_recovery_context');
    expect(ctx).not.toHaveProperty('confidence');
  });
});

describe('buildAssessedContext — this is context, never a veto (brief §7)', () => {
  it('a RECOVER-shaped day still returns advisory fields only, no blocking flag', () => {
    const ctx = buildAssessedContext(
      todayRow({ capacity_state: 'red', regulation_state: 'overloaded', executive_function: 'very_difficult' }),
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
