import { describe, it, expect } from 'vitest';
import { computeSleepTile } from '../sleep-tile';

describe('computeSleepTile', () => {
  it('shows the CPAP answer first and never as a failure', () => {
    expect(computeSleepTile(true, null, null)).toEqual({ band: 'good', detail: 'CPAP used last night' });
    expect(computeSleepTile(false, null, null)).toEqual({ band: 'moderate', detail: 'CPAP not used last night' });
  });

  it('prefers the CPAP answer over an older sleep-hours answer from the same day', () => {
    expect(computeSleepTile(true, 'under_5', null).detail).toBe('CPAP used last night');
  });

  it('a skipped (null) CPAP answer falls back to the old sleep_state', () => {
    expect(computeSleepTile(null, '7_8', null)).toEqual({ band: 'good', detail: '7-8h' });
    expect(computeSleepTile(null, 'under_5', null).band).toBe('rest');
  });

  it('falls back to the analytics row, then to Not recorded', () => {
    expect(computeSleepTile(null, null, { sleep_hours: 6, sleep_quality: 'Good', cpap_status: 'yes' }))
      .toEqual({ band: 'moderate', detail: '6h · Good · CPAP compliant' });
    expect(computeSleepTile(null, null, null)).toEqual({ band: 'unknown', detail: 'Not recorded' });
  });
});
