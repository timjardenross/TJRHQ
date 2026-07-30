import { describe, it, expect } from 'vitest';
import * as mockData from '@/lib/mockData';

// STARSHIP-REDESIGN.md trust-hardening pass: the /stage-progression page and
// the /medical Stage tab both presented this hardcoded record as if it were
// a real assessment. Both were retired/removed. This test proves the mock
// data itself is gone too, not just unreferenced - a future page could
// otherwise re-import it and reintroduce the exact same hazard silently.
describe('stage mock data removal', () => {
  it('mockData no longer exports stageProgressionRecord', () => {
    expect((mockData as Record<string, unknown>).stageProgressionRecord).toBeUndefined();
  });

  it('mockData no longer exports stageStatus', () => {
    expect((mockData as Record<string, unknown>).stageStatus).toBeUndefined();
  });
});
