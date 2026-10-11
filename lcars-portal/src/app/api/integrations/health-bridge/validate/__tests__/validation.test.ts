import { describe, expect, it } from 'vitest';
import { canonicalJson, validateHealthBridgeSummary } from '../validation';

const valid = () => ({
  schema_version: '1.0',
  date: '2026-10-10',
  timezone: 'Australia/Melbourne',
  activity: { steps: 2263, walking_distance_km: 1.7 },
  recovery: { resting_heart_rate_bpm: 66, hrv_sdnn_ms: 42 },
  sleep: { duration_minutes: 420, source: 'manual' },
  workouts: [{ duration_minutes: 35, type: 'walking' }],
  quality: { activity: 'valid', recovery: 'partial', sleep: 'corrected' },
});

describe('Health Bridge synthetic contract validation', () => {
  it('accepts the minimal summary and optional measurements', () => {
    expect(validateHealthBridgeSummary(valid()).issues).toEqual([]);
  });

  it('accepts omitted measurements and preserves explicit zero', () => {
    expect(validateHealthBridgeSummary({ schema_version: '1.0', date: '2026-10-10', timezone: 'Australia/Melbourne' }).issues).toEqual([]);
    expect(validateHealthBridgeSummary({ ...valid(), activity: { steps: 0 } }).issues).toEqual([]);
  });

  it.each([
    ['unknown field', { ...valid(), email: 'captain@example.com' }],
    ['unsupported version', { ...valid(), schema_version: '2.0' }],
    ['invalid units/range', { ...valid(), activity: { walking_distance_km: -1 } }],
    ['negative steps', { ...valid(), activity: { steps: -1 } }],
    ['non-integer steps', { ...valid(), activity: { steps: 1.5 } }],
    ['invalid date', { ...valid(), date: '2026-02-30' }],
    ['invalid timezone', { ...valid(), timezone: 'Not/A_Timezone' }],
    ['invalid sleep source', { ...valid(), sleep: { duration_minutes: 420, source: 'combined' } }],
    ['missing workout duration', { ...valid(), workouts: [{}] }],
    ['unknown workout field', { ...valid(), workouts: [{ duration_minutes: 20, calories: 100 }] }],
    ['out-of-range heart rate', { ...valid(), recovery: { resting_heart_rate_bpm: 500 } }],
  ])('rejects %s', (_label, payload) => {
    expect(validateHealthBridgeSummary(payload).issues.length).toBeGreaterThan(0);
  });

  it('rejects malformed top-level values and invalid quality states', () => {
    expect(validateHealthBridgeSummary(null).issues.length).toBeGreaterThan(0);
    expect(validateHealthBridgeSummary({ ...valid(), quality: { activity: 'fabricated' } }).issues.length).toBeGreaterThan(0);
  });

  it('canonicalizes object key order for deterministic retry hashing', () => {
    expect(canonicalJson({ b: 2, a: { d: 4, c: 3 } })).toBe('{"a":{"c":3,"d":4},"b":2}');
  });
});
