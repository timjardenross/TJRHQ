import { describe, it, expect } from 'vitest';
import { newlyAppeared } from '@/lib/alertAnnounce';

const a = (id: string) => ({ id });

describe('newlyAppeared', () => {
  it('announces nothing on the first look', () => {
    expect(newlyAppeared(null, [a('1'), a('2')])).toEqual([]);
  });

  it('returns only alerts that were not seen before', () => {
    expect(newlyAppeared(new Set(['1']), [a('1'), a('2')])).toEqual([a('2')]);
  });

  it('returns nothing when nothing changed or alerts only left', () => {
    expect(newlyAppeared(new Set(['1', '2']), [a('1')])).toEqual([]);
  });
});
