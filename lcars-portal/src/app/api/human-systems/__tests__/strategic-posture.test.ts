import { describe, it, expect } from 'vitest';
import { computeStrategicPosture, type BurnoutWindowRow } from '../strategic-posture';

// TypeScript mirror of core/health/test_burnout_trajectory.py — same
// scenarios, same expected outcomes, verifying the two language
// implementations of the V3 Mission 1 trajectory engine stay in lock-step
// (see strategic-posture.ts's header comment). If a threshold changes in
// one file without the other, these tests and the Python ones should both
// need updating together.

function capacityRow(day: number, capacityState: string, extra: Partial<BurnoutWindowRow> = {}): BurnoutWindowRow {
  const d = String(day).padStart(2, '0');
  return {
    checkin_type: 'capacity',
    log_date: `2026-08-${d}`,
    captured_at: `2026-08-${d}T09:00:00+10:00`,
    capacity_state: capacityState,
    executive_function: null,
    stimulation_state: null,
    compensation_load: null,
    recovery_duration: null,
    capacity_debt: null,
    ...extra,
  };
}

function eveningRow(day: number, capacityDebt: string): BurnoutWindowRow {
  const d = String(day).padStart(2, '0');
  return {
    checkin_type: 'evening',
    log_date: `2026-08-${d}`,
    captured_at: `2026-08-${d}T21:00:00+10:00`,
    capacity_state: null,
    executive_function: null,
    stimulation_state: null,
    compensation_load: null,
    recovery_duration: null,
    capacity_debt: capacityDebt,
  };
}

describe('computeStrategicPosture — insufficient data (Rule F / Scenario 5)', () => {
  it('fewer than 5 relevant check-ins yields insufficient_data, low confidence', () => {
    const checkins = [1, 2, 3].map((d) => capacityRow(d, 'red'));
    const profile = computeStrategicPosture(checkins, 21, 'ENGAGE');
    expect(profile.system_trajectory).toBe('insufficient_data');
    expect(profile.trajectory_confidence).toBe('low');
    expect(profile.current_recovery_stage).toBeNull();
    expect(profile.relevant_checkin_count).toBe(3);
  });

  it('falls back to today posture when insufficient data', () => {
    const checkins = [1, 2].map((d) => capacityRow(d, 'green'));
    const profile = computeStrategicPosture(checkins, 21, 'PROTECT');
    expect(profile.strategic_posture).toBe('protect');
  });

  it('defaults to steady with no today posture at all', () => {
    const profile = computeStrategicPosture([], 21, null);
    expect(profile.system_trajectory).toBe('insufficient_data');
    expect(profile.strategic_posture).toBe('steady');
  });
});

describe('computeStrategicPosture — Scenario 1: green day during sustained strain', () => {
  it('sustained_high_strain caps posture below engage even on a green today', () => {
    const checkins: BurnoutWindowRow[] = [
      ...[1, 2, 3, 4, 5, 6, 7].map((d) => capacityRow(d, 'orange')),
      capacityRow(8, 'red'),
      capacityRow(9, 'red'),
      capacityRow(10, 'green'), // today — a good day
      eveningRow(3, 'yes'),
      eveningRow(6, 'yes'),
    ];
    const profile = computeStrategicPosture(checkins, 21, 'ENGAGE');
    expect(profile.system_trajectory).toBe('sustained_high_strain');
    expect(profile.strategic_posture).not.toBe('engage');
    expect(['protect', 'recover', 'stabilise']).toContain(profile.strategic_posture);
    expect(profile.strategic_posture_message).not.toMatch(/%/);
    expect(profile.strategic_posture_message.toLowerCase()).not.toMatch(/score/);
  });

  it('burnout_like_depletion caps posture at recover', () => {
    const checkins: BurnoutWindowRow[] = [
      ...[1, 2, 3, 4, 5, 6].map((d) => capacityRow(d, 'red', { compensation_load: 'extreme' })),
      capacityRow(7, 'orange', { compensation_load: 'high' }),
      capacityRow(8, 'orange', { compensation_load: 'high' }),
      eveningRow(2, 'yes'),
      eveningRow(4, 'yes'),
      eveningRow(6, 'yes'),
    ];
    const profile = computeStrategicPosture(checkins, 21, 'ENGAGE');
    expect(profile.system_trajectory).toBe('burnout_like_depletion');
    expect(profile.strategic_posture).toBe('recover');
    expect(profile.current_recovery_stage).toBe('recover');
  });
});

describe('computeStrategicPosture — recovery_trajectory', () => {
  it('a clearly improving window can reach rebuilding', () => {
    const checkins: BurnoutWindowRow[] = [
      capacityRow(1, 'orange'), capacityRow(2, 'orange'), capacityRow(3, 'orange'),
      capacityRow(4, 'green'), capacityRow(5, 'green'),
      ...[6, 7, 8, 9, 10, 11].map((d) => capacityRow(d, 'green')),
    ];
    const profile = computeStrategicPosture(checkins, 21, 'ENGAGE');
    expect(profile.recovery_trajectory).toBe('improving');
    expect(['rebuilding', 'recovery_signals_emerging']).toContain(profile.system_trajectory);
    expect(['rebuild', 're_engage', 'stabilise']).toContain(profile.strategic_posture);
  });

  it('a clearly deteriorating window elevates concern and never reaches engage', () => {
    const checkins: BurnoutWindowRow[] = [
      ...[1, 2, 3, 4, 5].map((d) => capacityRow(d, 'green')),
      ...[6, 7, 8, 9].map((d) => capacityRow(d, 'orange')),
      capacityRow(10, 'green'), capacityRow(11, 'green'),
    ];
    const profile = computeStrategicPosture(checkins, 21, 'STEADY');
    expect(profile.recovery_trajectory).toBe('deteriorating');
    expect(profile.system_trajectory).not.toBe('stable');
    expect(profile.strategic_posture).not.toBe('engage');
  });
});

describe('computeStrategicPosture — Rule C, functional accessibility (Scenario 3)', () => {
  it('worsening executive function elevates concern despite stable green capacity', () => {
    const checkins: BurnoutWindowRow[] = [
      capacityRow(1, 'green', { executive_function: 'good', stimulation_state: 'balanced' }),
      capacityRow(2, 'green', { executive_function: 'good', stimulation_state: 'balanced' }),
      capacityRow(3, 'green', { executive_function: 'strained', stimulation_state: 'balanced' }),
      capacityRow(4, 'green', { executive_function: 'difficult', stimulation_state: 'high' }),
      capacityRow(5, 'green', { executive_function: 'very_difficult', stimulation_state: 'high' }),
      capacityRow(6, 'green', { executive_function: 'very_difficult', stimulation_state: 'low' }),
    ];
    const profile = computeStrategicPosture(checkins, 21, 'ENGAGE');
    expect(profile.system_trajectory).not.toBe('stable');
    expect(profile.contributing_signals.ef_worsening).toBe(true);
  });
});

describe('computeStrategicPosture — legacy rows with missing V3 fields', () => {
  it('bare legacy rows do not throw', () => {
    const checkins: BurnoutWindowRow[] = [
      { checkin_type: 'capacity', capacity_state: 'green', executive_function: null, stimulation_state: null, compensation_load: null, recovery_duration: null, capacity_debt: null, log_date: null, captured_at: null },
      { checkin_type: 'capacity', capacity_state: 'green', executive_function: null, stimulation_state: null, compensation_load: null, recovery_duration: null, capacity_debt: null, log_date: null, captured_at: null },
      { checkin_type: 'capacity', capacity_state: 'orange', executive_function: null, stimulation_state: null, compensation_load: null, recovery_duration: null, capacity_debt: null, log_date: null, captured_at: null },
      { checkin_type: 'capacity', capacity_state: 'green', executive_function: null, stimulation_state: null, compensation_load: null, recovery_duration: null, capacity_debt: null, log_date: null, captured_at: null },
      { checkin_type: 'capacity', capacity_state: 'green', executive_function: null, stimulation_state: null, compensation_load: null, recovery_duration: null, capacity_debt: null, log_date: null, captured_at: null },
    ];
    expect(() => computeStrategicPosture(checkins, 21, null)).not.toThrow();
    const profile = computeStrategicPosture(checkins, 21, null);
    expect(['low', 'moderate', 'high']).toContain(profile.trajectory_confidence);
  });

  it('an empty window returns insufficient_data, not a crash', () => {
    const profile = computeStrategicPosture([], 21, 'UNKNOWN');
    expect(profile.system_trajectory).toBe('insufficient_data');
    expect(profile.relevant_checkin_count).toBe(0);
  });
});
