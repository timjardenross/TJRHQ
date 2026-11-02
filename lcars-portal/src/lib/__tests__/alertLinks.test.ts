import { describe, it, expect } from 'vitest';
import { bomProductLink } from '@/lib/alertLinks';

describe('bomProductLink', () => {
  it('takes the last http line and uses the public host', () => {
    expect(bomProductLink('bom_vic', 'text\nhttp://reg.bom.gov.au/products/IDV21033.shtml')).toBe('https://www.bom.gov.au/products/IDV21033.shtml');
  });
  it('is only for BOM sources with a link', () => {
    expect(bomProductLink('vic_emergency', 'x\nhttps://example.com')).toBeNull();
    expect(bomProductLink('bom_qld', 'no link here')).toBeNull();
    expect(bomProductLink('bom_qld', null)).toBeNull();
  });
});
