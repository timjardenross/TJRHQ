import { describe, it, expect } from 'vitest';
import { collectSourceOutcomes } from '@/lib/sourceResults';

describe('collectSourceOutcomes', () => {
  it('flattens items from all successful sources with no failures', () => {
    const { items, failed } = collectSourceOutcomes([
      { source: 'Missions', ok: true, items: [1, 2] },
      { source: 'Health', ok: true, items: [3] },
    ]);
    expect(items).toEqual([1, 2, 3]);
    expect(failed).toEqual([]);
  });

  it('records failed source labels while keeping the rows of healthy sources', () => {
    const { items, failed } = collectSourceOutcomes([
      { source: 'Missions', ok: true, items: ['a'] },
      { source: 'Captures', ok: false, items: [] },
      { source: 'Events', ok: false, items: [] },
    ]);
    expect(items).toEqual(['a']);
    expect(failed).toEqual(['Captures', 'Events']);
  });

  it('distinguishes an all-empty-but-healthy result from a failure', () => {
    const healthyButEmpty = collectSourceOutcomes([
      { source: 'Missions', ok: true, items: [] as number[] },
    ]);
    expect(healthyButEmpty.items).toEqual([]);
    expect(healthyButEmpty.failed).toEqual([]);

    const failedAndEmpty = collectSourceOutcomes([
      { source: 'Missions', ok: false, items: [] as number[] },
    ]);
    expect(failedAndEmpty.items).toEqual([]);
    expect(failedAndEmpty.failed).toEqual(['Missions']);
  });
});
