import { describe, it, expect } from 'vitest';
import { bomAttentionLevel, BOM_ATTENTION_LABEL } from '@/lib/bomAttention';

describe('bomAttentionLevel (mirror of core/platform/bom_attention.py)', () => {
  const cases: [string | null, string | null, 'high' | 'standard'][] = [
    ['Tropical Cyclone Warning for Queensland east coast', 'cyclone', 'high'],
    ['Severe Thunderstorm Warning for Sydney Metropolitan', 'storm', 'high'],
    ['Severe Weather Warning for Damaging Winds', 'severe_weather', 'high'],
    ['Tsunami Warning for Lord Howe Island', 'tsunami', 'high'],
    ['Tsunami Warning: No Threat to Australia', 'tsunami', 'standard'],
    ['Major Flood Warning for the Hawkesbury River', 'flood', 'high'],
    ['Moderate Flood Warning for the Macleay River', 'flood', 'high'],
    ['Minor Flood Warning for the Tumut River', 'flood', 'standard'],
    ['Flood Warning for the Murray River', 'flood', 'standard'],
    ['Flood Watch for the Southeast Coast', 'flood', 'standard'],
    ['Fire Weather Warning for Greater Hunter', 'bushfire', 'standard'],
    ['Gale Warning', 'storm', 'standard'],
    ['', null, 'standard'],
    [null, null, 'standard'],
    ['Advice for Coastal Communities', 'cyclone', 'high'],
  ];
  it.each(cases)('%s (%s) -> %s', (headline, type, expected) => {
    expect(bomAttentionLevel(headline, type)).toBe(expected);
  });

  it('labels', () => {
    expect(BOM_ATTENTION_LABEL.high).toBe('High attention');
    expect(BOM_ATTENTION_LABEL.standard).toBe('Standard');
  });
});
